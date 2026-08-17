"""Tests pour le filtre quillify (issue #111).

Quill ne restitue pas visuellement un <br> interne à un <p> lors du
chargement de contenu existant (quill.root.innerHTML = ...) : le texte
apparaît collé sur une seule ligne, illisible pour l'admin qui édite une
question. Le filtre scinde chaque <p> contenant un <br> en plusieurs <p>,
ce qui correspond à la représentation native de Quill pour du texte
multi-lignes et reste donc lisible une fois chargé dans l'éditeur.
"""

from qcm.templatetags.qcm_extras import quillify


class TestQuillify:
    def test_splits_inline_br_into_separate_paragraphs(self):
        html = "<p>Correction : A. VRAI<br>B. FAUX<br>C. VRAI</p>"
        assert (
            quillify(html) == "<p>Correction : A. VRAI</p><p>B. FAUX</p><p>C. VRAI</p>"
        )

    def test_preserves_paragraph_attributes(self):
        html = '<p class="foo">A<br>B</p>'
        assert quillify(html) == '<p class="foo">A</p><p class="foo">B</p>'

    def test_handles_self_closing_br_variants(self):
        html = "<p>A<br/>B<br />C</p>"
        assert quillify(html) == "<p>A</p><p>B</p><p>C</p>"

    def test_leaves_paragraphs_without_br_unchanged(self):
        html = "<p>Pas de retour à la ligne</p>"
        assert quillify(html) == html

    def test_only_splits_the_affected_paragraph(self):
        html = "<p>Intact</p><p>A<br>B</p>"
        assert quillify(html) == "<p>Intact</p><p>A</p><p>B</p>"

    def test_empty_input_returns_empty_string(self):
        assert quillify("") == ""
        assert quillify(None) == ""

    def test_br_outside_paragraph_untouched(self):
        html = "<p>A</p><br><p>B</p>"
        assert quillify(html) == html
