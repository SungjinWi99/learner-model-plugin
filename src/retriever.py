from .repository import read_observations


def retrieve(tags):
    wanted = set(tags)
    matched = [item for item in read_observations() if any(tag in wanted for tag in item["comp"])]
    return sorted(matched, key=lambda item: str(item["t1"]), reverse=True)[:8]
