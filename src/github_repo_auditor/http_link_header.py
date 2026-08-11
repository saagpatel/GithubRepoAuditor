from __future__ import annotations


def next_link_from_header(link_header: str) -> str | None:
    """Return the first ``rel=next`` target from a GitHub Link header.

    ``requests.Response.links`` remains the primary parser. This bounded,
    linear fallback accepts GitHub's standard Link shape and fails closed for
    malformed entries.
    """
    for raw_entry in link_header.split(","):
        entry = raw_entry.strip()
        if not entry.startswith("<"):
            continue
        target_end = entry.find(">")
        if target_end <= 1:
            continue
        target = entry[1:target_end]
        for raw_parameter in entry[target_end + 1 :].split(";"):
            name, separator, value = raw_parameter.partition("=")
            if (
                separator
                and name.strip().lower() == "rel"
                and value.strip().strip("\"'").lower() == "next"
            ):
                return target
    return None
