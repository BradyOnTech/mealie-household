/** The sizes a grocery product's photo is kept at: large to look at, and small for lists */
export type GroceryPhotoSize = "photo" | "thumb";

function UnknownToString(ukn: string | unknown) {
  return typeof ukn === "string" ? ukn : "";
}

export const useStaticRoutes = () => {
  const { $config } = useNuxtApp();
  const prefix = `${$config.public.SUB_PATH}/api`.replace("//", "/");

  // Methods to Generate reference urls for assets/images *
  function recipeImage(recipeId: string, version: string | unknown = "", key: string | number = 1) {
    return `${prefix}/media/recipes/${recipeId}/images/original.webp?rnd=${key}&version=${UnknownToString(version)}`;
  }

  function recipeSmallImage(recipeId: string, version: string | unknown = "", key: string | number = 1) {
    return `${prefix}/media/recipes/${recipeId}/images/min-original.webp?rnd=${key}&version=${UnknownToString(
      version,
    )}`;
  }

  function recipeTinyImage(recipeId: string, version: string | unknown = "", key: string | number = 1) {
    return `${prefix}/media/recipes/${recipeId}/images/tiny-original.webp?rnd=${key}&version=${UnknownToString(
      version,
    )}`;
  }

  function recipeTimelineEventImage(recipeId: string, timelineEventId: string) {
    return `${prefix}/media/recipes/${recipeId}/images/timeline/${timelineEventId}/original.webp`;
  }

  function recipeTimelineEventSmallImage(recipeId: string, timelineEventId: string) {
    return `${prefix}/media/recipes/${recipeId}/images/timeline/${timelineEventId}/min-original.webp`;
  }

  function recipeTimelineEventTinyImage(recipeId: string, timelineEventId: string) {
    return `${prefix}/media/recipes/${recipeId}/images/timeline/${timelineEventId}/tiny-original.webp`;
  }

  function recipeAssetPath(recipeId: string, assetName: string) {
    return `${prefix}/media/recipes/${recipeId}/assets/${assetName}`;
  }

  /** A preferred product's photo, or null when it has none. Its address changes with the photo, so phones can keep it. */
  function groceryProductPhoto(product: { id: string; photo?: string | null }, size: GroceryPhotoSize = "thumb") {
    return product.photo ? `${prefix}/households/groceries/products/${product.id}/photo/${size}?v=${encodeURIComponent(product.photo)}` : null;
  }

  /** A photo found or taken for a product, before the product is saved with it */
  function groceryDraftPhoto(token: string, size: GroceryPhotoSize = "thumb") {
    return `${prefix}/households/groceries/photos/${token}/${size}`;
  }

  return {
    recipeImage,
    recipeSmallImage,
    recipeTinyImage,
    recipeTimelineEventImage,
    recipeTimelineEventSmallImage,
    recipeTimelineEventTinyImage,
    recipeAssetPath,
    groceryProductPhoto,
    groceryDraftPhoto,
  };
};
