# EICAR: an industry-standard harmless test string every real antivirus
# engine also recognizes as "test malware" (https://www.eicar.org/).
_EICAR_SIGNATURE = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)


def scan_chunk_for_viruses(chunk: bytes) -> bool:
    """Returns True if `chunk` is clean.

    Placeholder — this is NOT a real virus scanner. A production deployment
    must replace this with a call to ClamAV (via clamd) or a cloud malware
    scanning API. It only recognizes the EICAR test string so the
    reject-on-detection code path is exercised by a real (if trivial) check
    rather than sitting completely untested.
    """
    return _EICAR_SIGNATURE not in chunk
