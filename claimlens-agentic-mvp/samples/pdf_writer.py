"""
A small wrapper around reportlab's canvas that handles automatic page
breaks and paragraph wrapping. Generating realistic 15-22 page claim
packets means writing many sections of unknown length (narratives,
itemised tables) without manually tracking y-coordinates everywhere --
that bookkeeping lives here once, instead of in every document
generator.
"""

from __future__ import annotations

import textwrap

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


class SimplePDFWriter:
    def __init__(self, path: str, top_margin: float = 72, bottom_margin: float = 60, left_margin: float = 72):
        self.path = path
        self.width, self.height = letter
        self.top_margin = top_margin
        self.bottom_margin = bottom_margin
        self.left_margin = left_margin
        self.c = canvas.Canvas(path, pagesize=letter)
        self.y = self.height - self.top_margin
        self.page_count = 1
        self.c.setFont("Helvetica", 10)

    def _check_break(self, needed: float = 14):
        if self.y - needed < self.bottom_margin:
            self.new_page()

    def new_page(self):
        self.c.showPage()
        self.c.setFont("Helvetica", 10)
        self.y = self.height - self.top_margin
        self.page_count += 1

    def add_title(self, text: str, size: int = 14):
        self._check_break(size + 10)
        self.c.setFont("Helvetica-Bold", size)
        self.c.drawString(self.left_margin, self.y, text)
        self.y -= size + 10
        self.c.setFont("Helvetica", 10)

    def add_subheading(self, text: str):
        self._check_break(16)
        self.c.setFont("Helvetica-Bold", 11)
        self.c.drawString(self.left_margin, self.y, text)
        self.y -= 18
        self.c.setFont("Helvetica", 10)

    def add_line(self, text: str, leading: float = 15):
        self._check_break(leading)
        self.c.drawString(self.left_margin, self.y, text)
        self.y -= leading

    def add_lines(self, lines: list[str], leading: float = 15):
        for line in lines:
            self.add_line(line, leading=leading)

    def add_paragraph(self, text: str, width_chars: int = 95, leading: float = 14):
        for wrapped_line in textwrap.wrap(text, width=width_chars):
            self.add_line(wrapped_line, leading=leading)
        self.y -= 6  # paragraph spacing

    def save(self):
        self.c.save()
