#!/usr/bin/env python3
"""Validate repository YAML files against the template schema."""

import sys
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = {
    "origin": {
        "url": str,
        "name": str,
        "last_upstream_commit": str,
        "license": str,
    },
    "fork": {
        "url": str,
        "name": str,
        "created_at": str,
    },
    "status": {
        "state": str,
        "last_touched": str,
        "ci_status": str,
    },
    "languages": list,
    "targets": {
        "architectures": list,
        "runtimes": list,
        "operating_systems": list,
    },
}

VALID_STATES = {"active", "life-support", "archived", "pending"}
VALID_CI_STATUSES = {"passing", "failing", "unknown"}
VALID_PRIORITIES = {"critical", "high", "normal", "low"}
VALID_ARCHITECTURES = {"amd64", "arm64"}
VALID_OS = {"linux"}


def validate_field(data: dict, path: str, expected_type: type) -> list[str]:
    """Validate a single field exists and has correct type."""
    errors = []
    keys = path.split(".")
    current = data
    
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            errors.append(f"Missing required field: {path}")
            return errors
        current = current[key]
    
    if not isinstance(current, expected_type):
        errors.append(f"Field '{path}' should be {expected_type.__name__}, got {type(current).__name__}")
    
    return errors


def validate_repo_yaml(file_path: Path) -> list[str]:
    """Validate a repository YAML file."""
    errors = []
    
    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"YAML parsing error: {e}"]
    except Exception as e:
        return [f"File read error: {e}"]
    
    if not isinstance(data, dict):
        return ["YAML root must be a dictionary"]
    
    # Check required fields
    for section, fields in REQUIRED_FIELDS.items():
        if section not in data:
            errors.append(f"Missing required section: {section}")
            continue
        
        if isinstance(fields, dict):
            for field, field_type in fields.items():
                errors.extend(validate_field(data, f"{section}.{field}", field_type))
        else:
            if not isinstance(data[section], fields):
                errors.append(f"Field '{section}' should be {fields.__name__}")
    
    # Validate enum values
    if "status" in data and isinstance(data["status"], dict):
        state = data["status"].get("state")
        if state and state not in VALID_STATES:
            errors.append(f"Invalid status.state '{state}'. Must be one of: {VALID_STATES}")
        
        ci_status = data["status"].get("ci_status")
        if ci_status and ci_status not in VALID_CI_STATUSES:
            errors.append(f"Invalid status.ci_status '{ci_status}'. Must be one of: {VALID_CI_STATUSES}")
    
    # Validate architectures
    if "targets" in data and isinstance(data["targets"], dict):
        archs = data["targets"].get("architectures", [])
        for arch in archs:
            if arch not in VALID_ARCHITECTURES:
                errors.append(f"Invalid architecture '{arch}'. Must be one of: {VALID_ARCHITECTURES}")
        
        oses = data["targets"].get("operating_systems", [])
        for os in oses:
            if os not in VALID_OS:
                errors.append(f"Invalid OS '{os}'. Must be one of: {VALID_OS}")
    
    # Validate priority if present
    if "metadata" in data and isinstance(data["metadata"], dict):
        priority = data["metadata"].get("priority")
        if priority and priority not in VALID_PRIORITIES:
            errors.append(f"Invalid metadata.priority '{priority}'. Must be one of: {VALID_PRIORITIES}")
    
    # Validate non-empty required string fields
    if "origin" in data and isinstance(data["origin"], dict):
        if not data["origin"].get("url"):
            errors.append("origin.url cannot be empty")
        if not data["origin"].get("name"):
            errors.append("origin.name cannot be empty")
        
        # Validate archived_date is null or a valid date string
        if "archived_date" in data["origin"]:
            archived_date = data["origin"]["archived_date"]
            if archived_date is not None and not isinstance(archived_date, str):
                errors.append("origin.archived_date must be null or a date string (YYYY-MM-DD)")
    
    if "fork" in data and isinstance(data["fork"], dict):
        if not data["fork"].get("url"):
            errors.append("fork.url cannot be empty")
        if not data["fork"].get("name"):
            errors.append("fork.name cannot be empty")
    
    if "languages" in data and isinstance(data["languages"], list):
        if not data["languages"] or not any(data["languages"]):
            errors.append("languages list cannot be empty")
    
    return errors


def main() -> int:
    """Validate all YAML files in repos/ directory."""
    repos_dir = Path(__file__).parent.parent / "repos"
    
    if not repos_dir.exists():
        print("Error: repos/ directory not found")
        return 1
    
    yaml_files = list(repos_dir.glob("*.yaml")) + list(repos_dir.glob("*.yml"))
    
    if not yaml_files:
        print("No YAML files found in repos/")
        return 0
    
    all_valid = True
    
    for yaml_file in sorted(yaml_files):
        errors = validate_repo_yaml(yaml_file)
        
        if errors:
            all_valid = False
            print(f"\n❌ {yaml_file.name}:")
            for error in errors:
                print(f"   - {error}")
        else:
            print(f"✅ {yaml_file.name}")
    
    if all_valid:
        print(f"\nAll {len(yaml_files)} repository file(s) valid.")
        return 0
    else:
        print("\nValidation failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
