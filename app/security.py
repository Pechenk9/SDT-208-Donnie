import hashlib
import hmac
import secrets


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)

    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )

    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}"
        f"${SCRYPT_DKLEN}${salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, dklen_text, salt_hex, digest_hex = (
            stored.split("$")
        )
        if algorithm != "scrypt":
            return False

        n, r, p, dklen = map(
            int,
            (n_text, r_text, p_text, dklen_text),
        )
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)

        if (
            n < 2
            or n > 2**18
            or n & (n - 1)
            or not 1 <= r <= 16
            or not 1 <= p <= 4
            or not 16 <= dklen <= 64
            or not 16 <= len(salt) <= 64
            or len(expected_digest) != dklen
            or 128 * n * r + 256 * r * p > SCRYPT_MAXMEM
        ):
            return False

        actual_digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=dklen,
            maxmem=SCRYPT_MAXMEM,
        )

        return hmac.compare_digest(actual_digest, expected_digest)

    except (AttributeError, TypeError, ValueError, OverflowError):
        return False
