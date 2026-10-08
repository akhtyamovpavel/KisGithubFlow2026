import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_PIXELS = 40_000_000
SUPPORTED_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


class InvalidImageError(ValueError):
    pass


def sanitize_image(content: bytes) -> tuple[bytes, str, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image_format = image.format
                width, height = image.size

                if image_format not in SUPPORTED_FORMATS:
                    message = "Only JPEG, PNG and WebP images are allowed"
                    raise InvalidImageError(message)

                if width * height > MAX_IMAGE_PIXELS:
                    raise InvalidImageError("Image dimensions are too large")

                image.verify()

            with Image.open(BytesIO(content)) as image:
                image.load()
                output = BytesIO()
                content_type, extension = SUPPORTED_FORMATS[image_format]

                if image_format == "JPEG":
                    image = image.convert("RGB")
                    image.save(output, format="JPEG", quality=90, optimize=True)
                elif image_format == "PNG":
                    image.save(output, format="PNG", optimize=True)
                else:
                    image.save(output, format="WEBP", quality=90)

    except InvalidImageError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise InvalidImageError("The uploaded file is not a valid image") from error

    return output.getvalue(), content_type, extension
