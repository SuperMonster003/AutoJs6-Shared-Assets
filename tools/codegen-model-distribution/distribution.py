"""Reproducible, offline-reviewed codegen model catalogs and immutable assets."""

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import urlsplit


DEFAULT_REPOSITORY = "SuperMonster003/AutoJs6-Shared-Assets"
TINY_TEST_MODEL_ID = "autojs6.codegen.tiny-test"
CATALOG_FILE = "catalog-v1.json"
MAX_CATALOG_BYTES = 8 * 1024 * 1024
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
RELEASE_TAG_PATTERN = re.compile(r"codegen-models-v([1-9][0-9]*)")
OUTPUT_MARKER = ".codegen-model-distribution-output"


class DistributionError(ValueError):
    """A validation failure that can be shown without a Python traceback."""


def _load_package_module():
    key = "autojs6_codegen_package_validation"
    path = Path(__file__).with_name("package_validation.py").resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise DistributionError("Unexpected model package validator module identity")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


_package = _load_package_module()


def canonical_json_bytes(value):
    try:
        return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, UnicodeError) as error:
        raise DistributionError("Cannot serialize finite UTF-8 JSON: " + str(error)) from error


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def inherit_parent_acl(path):
    """Give a staging directory or a moved file the Windows access rights of a plain mkdir in its parent.

    Since the CVE-2024-4030 fix (Python 3.12.4 and 3.13), tempfile.mkdtemp() on Windows sets a
    protected DACL that allows only SYSTEM, Administrators and OWNER RIGHTS. Files created inside
    inherit it and a rename keeps it, so a signature written from an elevated window ends up owned by
    Administrators and unreadable for Git. An empty, unprotected DACL keeps only the entries
    inherited from the parent (what icacls /reset does). Other platforms are left untouched.
    """
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    initialize = advapi32.InitializeAcl
    initialize.argtypes, initialize.restype = (ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD), wintypes.BOOL
    apply = advapi32.SetNamedSecurityInfoW
    apply.argtypes = (wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD) + (ctypes.c_void_p,) * 4
    apply.restype = wintypes.DWORD
    # An empty ACL, never a NULL one: a NULL DACL would grant everyone full access.
    acl = ctypes.create_string_buffer(8)  # sizeof(ACL)
    if not initialize(acl, len(acl), 2):  # ACL_REVISION
        raise ctypes.WinError(ctypes.get_last_error())
    # SE_FILE_OBJECT, DACL_SECURITY_INFORMATION | UNPROTECTED_DACL_SECURITY_INFORMATION
    error = apply(str(path), 1, 0x20000004, None, None, acl, None)
    if error:
        raise OSError(None, ctypes.FormatError(error), str(path), error)


def read_json(path):
    path = Path(path)
    try:
        if path.stat().st_size > MAX_CATALOG_BYTES:
            raise DistributionError("JSON input exceeds the size limit")
        with path.open("rb") as source:
            content = source.read(MAX_CATALOG_BYTES + 1)
        if len(content) > MAX_CATALOG_BYTES:
            raise DistributionError("JSON input exceeds the size limit")
        return _package.parse_json(content)
    except (OSError, _package.PackageValidationError) as error:
        raise DistributionError(f"Cannot read JSON {path}: {error}") from error


def validate_package(path):
    try:
        return _package.validate_package(path)
    except (_package.PackageValidationError, OSError) as error:
        raise DistributionError(str(error)) from error


def inspect_package(path):
    try:
        return _package.inspect_package(path)
    except (_package.PackageValidationError, OSError) as error:
        raise DistributionError(str(error)) from error


def compare_release_version(manifest, model, version):
    try:
        _package.compare_release_version(manifest, model, version)
    except _package.PackageValidationError as error:
        raise DistributionError(str(error)) from error


def _repository(value):
    if not isinstance(value, str) or REPOSITORY_PATTERN.fullmatch(value) is None:
        raise DistributionError("repository must be a GitHub owner/repository name")
    return value


def _test_policy(repository, allow_test_models):
    if type(allow_test_models) is not bool:
        raise DistributionError("allow_test_models must be boolean")
    if allow_test_models and repository.casefold() == DEFAULT_REPOSITORY.casefold():
        raise DistributionError("Test-model mode is forbidden in the canonical repository")


def artifact_file_name(model_id, version_code, digest):
    return f"autojs6-codegen-{model_id}-v{version_code}-{digest[:8]}.ajcgm"


def artifact_url(repository, release_tag, filename):
    return f"https://github.com/{repository}/releases/download/{release_tag}/{filename}"


def _url(value, repository, filename, catalog_version):
    _package.text(value, "artifact URL", 2048)
    parsed = urlsplit(value)
    prefix = f"/{repository}/releases/download/"
    if (parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment
            or not parsed.path.startswith(prefix)):
        raise DistributionError("Artifact URL must use this repository's HTTPS GitHub Releases")
    remainder = parsed.path[len(prefix):].split("/")
    match = RELEASE_TAG_PATTERN.fullmatch(remainder[0]) if len(remainder) == 2 else None
    if match is None or remainder[1] != filename or int(match.group(1)) > catalog_version:
        raise DistributionError("Artifact URL must name this content-addressed file in this or an earlier release")
    return int(match.group(1))


def _versions(catalog):
    return {(model["modelId"], version["versionCode"]): version
            for model in catalog["models"] for version in model["versions"]}


def _immutable_version(version):
    return {key: value for key, value in version.items() if key not in ("deprecated", "revoked")}


def _validate_catalog(catalog, minimum_catalog_version, previous_catalog, expected_repository, allow_test_models):
    _package.fields(catalog, ("schemaVersion", "catalogVersion", "releaseTag", "generatedAt", "repository", "models"))
    if type(catalog["schemaVersion"]) is not int or catalog["schemaVersion"] != 1:
        raise DistributionError("Unsupported catalog schemaVersion")
    _package.integer(minimum_catalog_version, "minimum catalog version")
    version = _package.integer(catalog["catalogVersion"], "catalogVersion", minimum_catalog_version)
    if catalog["releaseTag"] != f"codegen-models-v{version}":
        raise DistributionError("releaseTag must match catalogVersion")
    generated = _package.timestamp(catalog["generatedAt"], "generatedAt")
    repository = _repository(catalog["repository"])
    _test_policy(repository, allow_test_models)
    if expected_repository is not None and repository != expected_repository:
        raise DistributionError("Signed catalog repository differs from the expected repository")
    if not isinstance(catalog["models"], list) or len(catalog["models"]) > 4096:
        raise DistributionError("models must be a bounded array")
    model_ids, artifacts = set(), set()
    for model in catalog["models"]:
        _package.fields(model, ("modelId", "displayName", "summary", "versions", "recommendedVersionCode"))
        model_id = _package.text(model["modelId"], "modelId", 64)
        if _package.MODEL_ID_PATTERN.fullmatch(model_id) is None or model_id in model_ids:
            raise DistributionError("Invalid or duplicate modelId")
        model_ids.add(model_id)
        if model_id == TINY_TEST_MODEL_ID and not allow_test_models:
            raise DistributionError("tiny-test models require explicit test mode on a noncanonical repository")
        _package.language_map(model["displayName"], "displayName")
        _package.language_map(model["summary"], "summary", 1024)
        if not isinstance(model["versions"], list) or not 1 <= len(model["versions"]) <= 4096:
            raise DistributionError("Model versions must be a nonempty bounded array")
        version_codes, eligible = set(), []
        for item in model["versions"]:
            _package.fields(item, ("versionCode", "versionName", "featureSchemaVersion", "featureNamesHash", "minHostVersionCode",
                                   "artifact", "releasedAt", "datasetId", "metrics", "license"), ("deprecated", "revoked"))
            code = _package.integer(item["versionCode"], "versionCode")
            if code in version_codes:
                raise DistributionError("Duplicate model versionCode")
            version_codes.add(code)
            for field in ("featureSchemaVersion", "minHostVersionCode"):
                _package.integer(item[field], field)
            _package.text(item["versionName"], "versionName", 256)
            _package.text(item["datasetId"], "datasetId")
            if not isinstance(item["featureNamesHash"], str) or not _package.NAME_HASH_PATTERN.fullmatch(item["featureNamesHash"]):
                raise DistributionError("Invalid featureNamesHash")
            if _package.timestamp(item["releasedAt"], "releasedAt") > generated:
                raise DistributionError("releasedAt cannot be later than catalog generatedAt")
            _package.metrics_summary(item["metrics"])
            _package.fields(item["license"], ("spdx",))
            license_name = _package.text(item["license"]["spdx"], "SPDX expression", 256)
            if "licenseref-localevaluation" in license_name.casefold():
                raise DistributionError("Local-evaluation packages cannot enter a release catalog")
            for flag in ("deprecated", "revoked"):
                if flag in item and type(item[flag]) is not bool:
                    raise DistributionError(flag + " must be boolean")
            if not item.get("deprecated", False) and not item.get("revoked", False):
                eligible.append(code)
            artifact = item["artifact"]
            _package.fields(artifact, ("fileName", "size", "sha256", "url", "urls"))
            _package.integer(artifact["size"], "package size", 1, MAX_PACKAGE_BYTES - 1)
            if not isinstance(artifact["sha256"], str) or not _package.SHA256_PATTERN.fullmatch(artifact["sha256"]):
                raise DistributionError("Invalid package SHA-256")
            expected_name = artifact_file_name(model_id, code, artifact["sha256"])
            if artifact["fileName"] != expected_name or expected_name in artifacts:
                raise DistributionError("Invalid or duplicate content-addressed fileName")
            artifacts.add(expected_name)
            _url(artifact["url"], repository, expected_name, version)
            urls = artifact["urls"]
            if (not isinstance(urls, list) or not 1 <= len(urls) <= 16 or urls[0] != artifact["url"]
                    or any(not isinstance(url, str) for url in urls) or len(set(urls)) != len(urls)):
                raise DistributionError("artifact.urls must start with url and contain distinct URLs")
            for url in urls:
                _url(url, repository, expected_name, version)
        recommended = model["recommendedVersionCode"]
        if recommended is not None:
            _package.integer(recommended, "recommendedVersionCode")
        if recommended != (max(eligible) if eligible else None):
            raise DistributionError("recommendedVersionCode must be the latest active version or null")
        if [item["versionCode"] for item in model["versions"]] != sorted(version_codes):
            raise DistributionError("Versions must use ascending versionCode order")
    if [model["modelId"] for model in catalog["models"]] != sorted(model_ids):
        raise DistributionError("Models must use ascending modelId order")
    if len(canonical_json_bytes(catalog)) > MAX_CATALOG_BYTES:
        raise DistributionError("Catalog exceeds its byte-size limit")
    if previous_catalog is not None:
        _validate_catalog(previous_catalog, 1, None, repository, allow_test_models)
        previous_version = previous_catalog["catalogVersion"]
        if version < previous_version:
            raise DistributionError("Catalog rollback is forbidden")
        if version == previous_version and canonical_json_bytes(catalog) != canonical_json_bytes(previous_catalog):
            raise DistributionError("Same catalogVersion has different content")
        if generated < _package.timestamp(previous_catalog["generatedAt"], "previous generatedAt"):
            raise DistributionError("Catalog generatedAt moved backwards")
        current, previous = _versions(catalog), _versions(previous_catalog)
        for key, old in previous.items():
            if key not in current or _immutable_version(current[key]) != _immutable_version(old):
                raise DistributionError("Historical model version content changed or disappeared")
            for flag in ("deprecated", "revoked"):
                if old.get(flag, False) and not current[key].get(flag, False):
                    raise DistributionError("Historical " + flag + " status cannot be reversed")
        for key in current.keys() - previous.keys():
            earlier = [code for model_id, code in previous if model_id == key[0]]
            if earlier and key[1] <= max(earlier):
                raise DistributionError("New versions must exceed every previously recorded versionCode")
    return catalog


def validate_catalog(catalog, minimum_catalog_version=1, *, previous_catalog=None, expected_repository=None, allow_test_models=False):
    try:
        return _validate_catalog(catalog, minimum_catalog_version, previous_catalog, expected_repository, allow_test_models)
    except _package.PackageValidationError as error:
        raise DistributionError(str(error)) from error


def _under(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise DistributionError("Source path escapes its root")
    return path


def _source_metadata(path):
    value = read_json(path)
    try:
        _package.fields(value, ("format", "summary", "releasedAt"), ("deprecated", "revoked"))
        if type(value["format"]) is not int or value["format"] != 1:
            raise DistributionError("Unsupported source metadata format")
        _package.language_map(value["summary"], "summary", 1024)
        _package.timestamp(value["releasedAt"], "releasedAt")
        for flag in ("deprecated", "revoked"):
            if flag in value and type(value[flag]) is not bool:
                raise DistributionError("Source flags must be explicit booleans")
    except _package.PackageValidationError as error:
        raise DistributionError(str(error)) from error
    return value


def _require_gate(folder, inspection, repository, allow_test_models):
    manifest = inspection["manifest"]
    if manifest["modelId"] == TINY_TEST_MODEL_ID:
        if not allow_test_models or repository.casefold() == DEFAULT_REPOSITORY.casefold():
            raise DistributionError("tiny-test source is forbidden outside explicit fork/private test mode")
        return
    gate = read_json(_under(folder / "gate.json", folder))
    if (type(gate.get("format")) is not int or gate["format"] != 1 or gate.get("passed") is not True
            or gate.get("packageSha256") != inspection["sha256"]):
        raise DistributionError("Production models require a passed gate.json bound to the exact package SHA-256")


def _source_records(source_root, repository, allow_test_models):
    source_root = Path(source_root).resolve()
    if not source_root.is_dir():
        raise DistributionError("Model source root is missing")
    result, excluded = [], []
    for model_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        _under(model_dir, source_root)
        if not _package.MODEL_ID_PATTERN.fullmatch(model_dir.name):
            raise DistributionError("Invalid source model directory")
        if model_dir.name == TINY_TEST_MODEL_ID and not allow_test_models:
            excluded.append({"modelId": model_dir.name, "reason": "test-only source excluded from production catalog"})
            continue
        for folder in sorted(path for path in model_dir.iterdir() if path.is_dir()):
            _under(folder, source_root)
            if not re.fullmatch(r"[1-9][0-9]*", folder.name) or int(folder.name) > 2**31 - 1:
                raise DistributionError("Invalid source version directory")
            packages = list(folder.glob("*.ajcgm"))
            if len(packages) != 1:
                raise DistributionError("Each version source directory requires exactly one .ajcgm")
            package_path = _under(packages[0], folder)
            inspection = inspect_package(package_path)
            manifest = inspection["manifest"]
            if manifest["modelId"] != model_dir.name or manifest["versionCode"] != int(folder.name):
                raise DistributionError("Source path differs from package modelId/versionCode")
            if "licenseref-localevaluation" in manifest["license"].casefold():
                raise DistributionError("Local-evaluation packages cannot be distributed")
            metadata = _source_metadata(_under(folder / "source.json", folder))
            card = _under(folder / "MODEL_CARD.md", folder)
            if (not card.is_file() or card.stat().st_size != len(inspection["entries"]["MODEL_CARD.md"])
                    or card.read_bytes() != inspection["entries"]["MODEL_CARD.md"]):
                raise DistributionError("Source MODEL_CARD.md differs from package")
            dataset = read_json(_under(folder / "dataset-manifest.json", folder))
            splits = dataset.get("splits")
            train = splits.get("train") if isinstance(splits, dict) else None
            if not isinstance(train, dict):
                raise DistributionError("Public dataset manifest must include train statistics")
            if (dataset.get("datasetId") != manifest["dataset"]["datasetId"]
                    or dataset.get("generatedAt") != manifest["dataset"]["createdAt"]
                    or type(train.get("groups")) is not int or type(train.get("groupsWithoutCandidates")) is not int
                    or not 0 <= train["groupsWithoutCandidates"] <= train["groups"] <= 2**31 - 1
                    or train["groups"] - train["groupsWithoutCandidates"] != manifest["dataset"]["groups"]):
                raise DistributionError("Public dataset manifest summary differs from package")
            _require_gate(folder, inspection, repository, allow_test_models)
            result.append((package_path, inspection, metadata))
    return result, excluded


def prepare_catalog(source_root, output, repository, catalog_version, generated_at, *, previous_catalog=None,
                    allow_test_models=False, empty_bootstrap=False):
    """Stage an unsigned catalog; signing and all network publication are separate."""
    repository = _repository(repository)
    _test_policy(repository, allow_test_models)
    if type(empty_bootstrap) is not bool:
        raise DistributionError("empty_bootstrap must be boolean")
    if previous_catalog is not None and not isinstance(previous_catalog, dict):
        previous_catalog = read_json(previous_catalog)
    if previous_catalog is not None:
        validate_catalog(previous_catalog, expected_repository=repository, allow_test_models=allow_test_models)
    if type(catalog_version) is not int or not 1 <= catalog_version <= 2**31 - 1:
        raise DistributionError("catalogVersion must be a positive signed-32-bit integer")
    if previous_catalog is None and catalog_version != 1:
        raise DistributionError("Catalog versions after v1 require --previous-catalog")
    if previous_catalog is not None and catalog_version != previous_catalog["catalogVersion"] + 1:
        raise DistributionError("Preparation must advance exactly one version beyond previous-catalog")
    models = {} if previous_catalog is None else {model["modelId"]: deepcopy(model) for model in previous_catalog["models"]}
    old_versions = {} if previous_catalog is None else _versions(previous_catalog)
    release_tag = f"codegen-models-v{catalog_version}"
    assets = {}
    records, excluded = ([], []) if empty_bootstrap else _source_records(source_root, repository, allow_test_models)
    if empty_bootstrap:
        models = {}  # History validation below prevents erasing a populated catalog.
    for package_path, inspection, metadata in records:
        manifest = inspection["manifest"]
        model_id, code = manifest["modelId"], manifest["versionCode"]
        key = (model_id, code)
        filename = artifact_file_name(model_id, code, inspection["sha256"])
        url = artifact_url(repository, release_tag, filename)
        artifact = {"fileName": filename, "size": inspection["size"], "sha256": inspection["sha256"], "url": url, "urls": [url]}
        if key in old_versions:
            artifact = deepcopy(old_versions[key]["artifact"])
            if artifact["sha256"] != inspection["sha256"] or artifact["size"] != inspection["size"]:
                raise DistributionError("Source attempts to replace an immutable historical package")
        else:
            assets[filename] = package_path
        version = {field: manifest[field] for field in ("versionCode", "versionName", "featureSchemaVersion", "featureNamesHash", "minHostVersionCode", "metrics")}
        version.update(artifact=artifact, releasedAt=metadata["releasedAt"], datasetId=manifest["dataset"]["datasetId"], license={"spdx": manifest["license"]})
        for flag in ("deprecated", "revoked"):
            if flag in metadata:
                version[flag] = metadata[flag]
        existing = models.setdefault(model_id, {"modelId": model_id, "displayName": manifest["displayName"],
                                                "summary": metadata["summary"], "versions": [], "recommendedVersionCode": None})
        versions = {item["versionCode"]: item for item in existing["versions"]}
        versions[code] = version
        existing["versions"] = [versions[value] for value in sorted(versions)]
        if code == max(versions):
            existing["displayName"], existing["summary"] = manifest["displayName"], metadata["summary"]
    for model in models.values():
        active = [version["versionCode"] for version in model["versions"] if not version.get("deprecated", False) and not version.get("revoked", False)]
        model["recommendedVersionCode"] = max(active) if active else None
    if not models and not empty_bootstrap:
        raise DistributionError("No release models remain; an empty initial catalog requires explicit --empty-bootstrap")
    catalog = {"schemaVersion": 1, "catalogVersion": catalog_version, "releaseTag": release_tag, "generatedAt": generated_at,
               "repository": repository, "models": [models[key] for key in sorted(models)]}
    validate_catalog(catalog, previous_catalog=previous_catalog, expected_repository=repository, allow_test_models=allow_test_models)
    output = Path(output).resolve()
    if output.exists():
        raise DistributionError("Output already exists; use a new pending/build directory")
    source_root = Path(source_root).resolve()
    if output == source_root or output.is_relative_to(source_root):
        raise DistributionError("Output must be outside the model source tree")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="." + output.name + "-", dir=output.parent))
    try:
        # Before anything is written, so every file inherits the access rights of the final directory.
        inherit_parent_acl(temporary)
        (temporary / "assets").mkdir()
        for filename, path in sorted(assets.items()):
            target = temporary / "assets" / filename
            shutil.copyfile(path, target)
            inspected = inspect_package(target)
            expected = next(version["artifact"] for model in catalog["models"] for version in model["versions"] if version["artifact"]["fileName"] == filename)
            if (inspected["size"], inspected["sha256"]) != (expected["size"], expected["sha256"]):
                raise DistributionError("Source package changed while staging")
        (temporary / CATALOG_FILE).write_bytes(canonical_json_bytes(catalog))
        (temporary / "release-assets.txt").write_text("".join(name + "\n" for name in sorted(assets)), encoding="utf-8", newline="\n")
        (temporary / "preparation.json").write_bytes(canonical_json_bytes({
            "format": 1, "repository": repository, "catalogVersion": catalog_version, "generatedAt": generated_at,
            "allowTestModels": allow_test_models, "emptyBootstrap": empty_bootstrap,
            "excludedTestSources": excluded, "releaseAssetCount": len(assets), "unsigned": True,
        }))
        (temporary / OUTPUT_MARKER).write_text("Unsigned codegen model release staging.\n", encoding="utf-8", newline="\n")
        if output.exists():
            raise DistributionError("Output appeared during staging")
        temporary.rename(output)
    finally:
        if temporary.exists():
            if not temporary.resolve().is_relative_to(output.parent.resolve()):
                raise DistributionError("Refusing staging cleanup outside output parent")
            shutil.rmtree(temporary)
    return catalog
