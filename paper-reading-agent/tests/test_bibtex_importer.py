import pytest
from backend.tools.bibtex_importer import parse_bibtex

VALID_BIBTEX = """@article{vaswani2017attention,
  title={Attention Is All You Need},
  author={Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
  year={2017},
  journal={Advances in Neural Information Processing Systems},
  volume={30}
}

@inproceedings{he2016deep,
  title={Deep Residual Learning for Image Recognition},
  author={He, Kaiming and Zhang, Xiangyu and Ren, Shaoqing and Sun, Jian},
  year={2016},
  booktitle={Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition},
  pages={770-778}
}"""


def test_parse_bibtex_valid():
    papers, errors = parse_bibtex(VALID_BIBTEX)
    assert len(papers) == 2
    assert len(errors) == 0
    assert papers[0].title == "Attention Is All You Need"
    assert len(papers[0].authors) >= 1
    assert papers[0].metadata.get("year") == 2017
    assert papers[0].import_source == "bib_import"
    assert papers[0].file_path is None


def test_parse_bibtex_empty_content():
    papers, errors = parse_bibtex("")
    assert len(papers) == 0


def test_parse_bibtex_malformed():
    papers, errors = parse_bibtex("this is not bibtex at all {{{")
    assert isinstance(papers, list)
    assert isinstance(errors, list)


def test_parse_bibtex_year_non_numeric():
    content = '@article{{test2025, title={{Test Paper}}, author={{Test, Author}}, year={{to appear}}}}'
    papers, errors = parse_bibtex(content)
    assert isinstance(papers, list)


def test_parse_bibtex_no_title():
    content = """@article{test2025,
      author={Test, Author},
      year={2025}
    }"""
    papers, errors = parse_bibtex(content)
    assert isinstance(papers, list)
