from dataclasses import dataclass


@dataclass(frozen=True)
class HashMethod:
    name: str
    version: int
    video_filter: str
    description: str


LEGACY_CENTER = "legacy-center"
FULL_FRAME = "full-frame"
DEFAULT_HASH_METHOD = LEGACY_CENTER

HASH_METHODS = {
    LEGACY_CENTER: HashMethod(
        name=LEGACY_CENTER,
        version=1,
        video_filter="crop=in_w/10:in_h/10:in_w*0.45:in_h*0.45",
        description="brightness of the central 10% x 10% crop",
    ),
    FULL_FRAME: HashMethod(
        name=FULL_FRAME,
        version=1,
        video_filter="scale=128:72:flags=fast_bilinear",
        description="brightness of the full frame downsampled to 128x72",
    ),
}


def get_hash_method(name: str) -> HashMethod:
    try:
        return HASH_METHODS[name]
    except KeyError as exc:
        raise ValueError(f"unknown hash method: {name}") from exc
