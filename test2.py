def generate_jazoest(lsd_token: str, version: int = 2, should_randomize: bool = False) -> str:
    total = sum(ord(c) for c in lsd_token)
    if should_randomize:
        return str(total)
    else:
        return str(version) + str(total)



print(generate_jazoest('AVrt2b2ueEs', 2, False ))