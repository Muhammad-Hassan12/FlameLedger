import numpy as np
import pytest

from backend.retrieval import BM25,fmt_doc,fmt_query,fuse,validate_matrix
from scripts.common import FORMATTING_VERSION,ordered_id_digest,sha256


def passages():
    return [{"id":"P-B","source_id":"S-B","title":"Flame","text":"burning flame experiment"},
            {"id":"P-A","source_id":"S-A","title":"Smoke","text":"smoke detector"}]


def test_zero_lexical_hits_return_no_rows_and_preserve_dense_ranking():
    rows=passages();lexical=BM25(rows).rank("zzzzunmatchedtoken")
    assert lexical == []
    assert fuse([],lexical,rows) == []
    assert [p["id"] for p in fuse([(0,.9),(1,.8)],lexical,rows)] == ["P-B","P-A"]


def test_rrf_ties_stable_by_passage_id_and_cap_per_source():
    rows=passages()
    result=fuse([(0,.9),(1,.8)],[(1,5),(0,2)],rows)
    assert [p["id"] for p in result] == ["P-A","P-B"]
    rows.append({**rows[0],"id":"P-C"})
    assert len(fuse([(0,1),(2,.9)],[],rows,per_source=1)) == 1


def test_formatters_match_notebook_without_prompt_stacking():
    assert fmt_query("  some\n question ") == "task: search result | query: some question"
    assert fmt_doc("  Some\n Title "," body\ntext ") == "title: Some Title | text: body\ntext"
    assert fmt_doc(None," x ") == "title: none | text: x"


def test_model_index_row_order_mismatch_is_fatal(tmp_path):
    rows=passages();vectors=np.zeros((2,768),dtype=np.float32);vectors[:,0]=1
    file=tmp_path/"vectors.npy";np.save(file,vectors,allow_pickle=False)
    manifest={"ordered_id_digest":ordered_id_digest(rows),"vectors_sha256":sha256(file),"formatting_version":FORMATTING_VERSION}
    validate_matrix(file,rows,manifest)
    with pytest.raises(ValueError,match="row-ID"):validate_matrix(file,list(reversed(rows)),manifest)
    vectors[0,0]=0;np.save(file,vectors,allow_pickle=False);manifest["vectors_sha256"]=sha256(file)
    with pytest.raises(ValueError,match="non-unit"):validate_matrix(file,rows,manifest)
