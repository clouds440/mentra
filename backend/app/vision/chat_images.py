"""Bounded raster preparation for direct chat vision, independent of OCR."""
import base64
from io import BytesIO
from PIL import Image, ImageOps
from app.core.exceptions import AppError


def prepare_chat_image(data: bytes) -> dict:
    try:
        with Image.open(BytesIO(data)) as original:
            if original.format not in ('PNG', 'JPEG', 'GIF', 'WEBP'):
                raise ValueError('Unsupported raster format')
            if original.width * original.height > 30_000_000:
                raise AppError('CHAT_IMAGE_SIZE', 'This image exceeds the pixel limit.', 422)
            # Preserve the original in storage; only the model input is resized.
            image = ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((1600, 1600))
            output = BytesIO()
            image.save(output, format='JPEG', quality=90)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise AppError('CHAT_IMAGE_UNREADABLE', 'This image could not be read. Upload a valid image.', 422) from error
    return dict(type='image_url', image_url=dict(
        url='data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii'), detail='high'))
