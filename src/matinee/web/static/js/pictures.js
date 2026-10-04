// Where each picture comes from. Matinee's own image route serves every picture by default. With TMDB as
// the image source, the server gives the TMDB path of each film's poster, and of the picked film's
// backdrop, and those pictures load straight from TMDB's image server; a film without a path keeps the
// image route. Every picture the page shows is asked for with CORS, so the glow can read its colour.

const TMDB = "https://image.tmdb.org/t/p/";
// Matinee's sizes as TMDB widths: the nearest TMDB width, never one far larger than the cell needs.
const TMDB_WIDTHS = {
  poster: { xs: "w92", s: "w154", m: "w342", l: "w780" },
  backdrop: { m: "w780", l: "w1280" },
};

// The TMDB poster paths an /api/pictures reply carries, by film.
export function posterPaths(reply) {
  return new Map(Object.entries(reply?.posters || {}).map(([id, path]) => [Number(id), path]));
}

// Whether `url` is a picture on TMDB's image server.
export function fromTmdb(url) {
  return url.startsWith(TMDB);
}

// The address of film `id`'s poster at `size`, given `paths` from posterPaths.
export function posterUrl(paths, id, size) {
  const path = paths.get(id);
  return path ? `${TMDB}${TMDB_WIDTHS.poster[size]}${path}` : `/img/poster/${id}/${size}`;
}

// The address of film `id`'s backdrop at `size`; `path` is the film card's TMDB backdrop path, or null.
export function backdropUrl(id, size, path) {
  return path ? `${TMDB}${TMDB_WIDTHS.backdrop[size]}${path}` : `/img/backdrop/${id}/${size}`;
}

// An image element whose picture may come from TMDB and still have its pixels read.
export function corsImage(img = new Image()) {
  img.crossOrigin = "anonymous";
  return img;
}
