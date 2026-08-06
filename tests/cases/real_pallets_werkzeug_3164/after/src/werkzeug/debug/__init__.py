

def hash_pin(pin: str) -> str:
    return hashlib.sha3_256(f"{pin} added salt".encode("utf-8", "replace")).hexdigest()[
        :12
    ]


_machine_id: str | bytes | None = None
    # within the unauthenticated debug page.
    private_bits = [str(uuid.getnode()), get_machine_id()]

    h = hashlib.sha3_256()
    for bit in chain(probably_public_bits, private_bits):
        if not bit:
            continue
