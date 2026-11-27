import ipaddress


def normalize_ip_address(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def is_valid_entity_value(entity_type: str, value: str) -> bool:
    return entity_type != "IP_ADDRESS" or normalize_ip_address(value) is not None
