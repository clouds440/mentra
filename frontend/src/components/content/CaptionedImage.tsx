import { memo } from 'react';
import { publicImageUrl } from '../../lib/imageUrls';
import { ImageAsset, ImageGallery, imageCaption, useImageGallery, type GalleryImage } from './ImageGallery';

export const CaptionedImage = memo(function CaptionedImage(props: GalleryImage & { index?: number }) {
  const gallery = useImageGallery();
  if (!gallery) return <ImageGallery images={[props]}><ImageFigure {...props} index={0} /></ImageGallery>;
  return <ImageFigure {...props} />;
});
function ImageFigure({ index = 0, ...image }: GalleryImage & { index?: number }) {
  const gallery = useImageGallery();
  const caption = imageCaption(image);
  const url = publicImageUrl(image.src, true);
  const source = image.source ? publicImageUrl(image.source, true) : null;
  return <figure className="markdown-image">
    {url ? <button type="button" aria-label={`Expand image: ${caption}`} className="image-open" onClick={() => gallery?.open(index)}><ImageAsset image={image} /></button> : <ImageAsset image={image} />}
    <figcaption dir="auto">{caption}{source && <> · <a href={source} rel="noopener noreferrer" target="_blank">Source</a></>}</figcaption>
  </figure>;
}
