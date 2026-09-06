class ManifestError(ValueError):
    pass


def validate_manifest(data: dict) -> None:
    required = ("schema_version", "analyzer", "source", "analysis_settings", "estimates", "events", "curves", "structure")
    missing = [key for key in required if key not in data]
    if missing:
        raise ManifestError(f"Missing manifest fields: {', '.join(missing)}")
    if data["schema_version"] != "0.1.0":
        raise ManifestError(f"Unsupported manifest schema version: {data['schema_version']}")
    source = data["source"]
    for key in ("id", "filename", "sha256", "duration_seconds", "sample_rate_hz", "channel_count"):
        if key not in source:
            raise ManifestError(f"Missing source.{key}")
    if source["duration_seconds"] <= 0 or source["sample_rate_hz"] <= 0 or source["channel_count"] <= 0:
        raise ManifestError("Source duration, sample rate and channel count must be positive")
    names = set()
    for curve in data["curves"]:
        for key in ("name", "source_id", "unit", "sample_interval_seconds", "values"):
            if key not in curve:
                raise ManifestError(f"Malformed curve: missing {key}")
        if curve["name"] in names:
            raise ManifestError(f"Duplicate curve: {curve['name']}")
        names.add(curve["name"])
        if curve["sample_interval_seconds"] <= 0 or not isinstance(curve["values"], list):
            raise ManifestError(f"Invalid curve: {curve['name']}")
