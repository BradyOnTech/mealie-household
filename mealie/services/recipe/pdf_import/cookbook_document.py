"""
The cookbook files an import can read, behind one interface: its pages' text, an image of a page
for the AI to read, and the photo that goes with a recipe.
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from .epub_document import EpubBook, EpubReadError, is_epub, read_epub, save_largest_image
from .pdf_document import PdfPage, PdfReadError, count_pages, extract_photo, read_pages, render_page, run_pdfium


class CookbookReadError(Exception):
    """The file isn't a cookbook that can be read: not a PDF or EPUB, damaged, or protected."""


class CookbookDocument(ABC):
    format: str

    layout_matters: bool
    """
    Whether the AI should see images of a recipe's pages, not just their text. A PDF's text can come
    out of reading order, but an EPUB's can't.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    @abstractmethod
    async def check(self) -> None:
        """Raises `CookbookReadError` if the file can't be read."""

    @abstractmethod
    async def read_pages(self) -> list[PdfPage]: ...

    @abstractmethod
    async def render_page(self, number: int, dest: Path) -> Path | None:
        """Saves an image of the page as a JPEG, for the AI to read. Returns None if there isn't one."""

    @abstractmethod
    async def extract_photo(self, numbers: Sequence[int], dest: Path) -> Path | None:
        """Saves the recipe photo on the given pages as a JPEG. Returns None if there isn't one."""


class PdfCookbook(CookbookDocument):
    format = "pdf"
    layout_matters = True

    async def check(self) -> None:
        try:
            await run_pdfium(count_pages, self.path)
        except PdfReadError as e:
            raise CookbookReadError(str(e)) from e

    async def read_pages(self) -> list[PdfPage]:
        return await run_pdfium(read_pages, self.path)

    async def render_page(self, number: int, dest: Path) -> Path | None:
        return await run_pdfium(render_page, self.path, number, dest)

    async def extract_photo(self, numbers: Sequence[int], dest: Path) -> Path | None:
        return await run_pdfium(extract_photo, self.path, list(numbers), dest)


class EpubCookbook(CookbookDocument):
    format = "epub"
    layout_matters = False

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._book: EpubBook | None = None

    async def _read(self) -> EpubBook:
        if self._book is None:
            try:
                self._book = await asyncio.to_thread(read_epub, self.path)
            except EpubReadError as e:
                raise CookbookReadError(str(e)) from e
        return self._book

    async def check(self) -> None:
        await self._read()

    async def read_pages(self) -> list[PdfPage]:
        return (await self._read()).pages

    async def render_page(self, number: int, dest: Path) -> Path | None:
        # a page without text is usually a scan, which is its own largest image
        book = await self._read()
        return await asyncio.to_thread(save_largest_image, self.path, book, [number], dest)

    async def extract_photo(self, numbers: Sequence[int], dest: Path) -> Path | None:
        book = await self._read()
        return await asyncio.to_thread(save_largest_image, self.path, book, numbers, dest)


def open_cookbook(path: Path) -> CookbookDocument:
    """Picks how to read the file from its contents, since its name can't be trusted to say."""

    return EpubCookbook(path) if is_epub(path) else PdfCookbook(path)
