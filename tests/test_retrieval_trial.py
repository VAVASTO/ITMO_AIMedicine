from itmo_aimedicine.retrieval_trial import exact_lookup, rank_bm25


def test_known_keys_never_return_another_scope_or_archived_revision():
    query={'query':'time','topic':'C02','scope':'adult','revision':'current'}
    corpus=[{'id':'valid','text':'time','topic':'C02','scope':'adult','revision':'current'},
            {'id':'old','text':'time','topic':'C02','scope':'adult','revision':'archive'},
            {'id':'other','text':'time','topic':'C02','scope':'child','revision':'current'}]
    assert exact_lookup(query,corpus)==['valid']
    assert exact_lookup({**query,'topic':'unknown'},corpus)==[]


def test_bm25_prefers_matching_content_and_preserves_all_candidates():
    query={'query':'рентгенография','topic':'unknown','scope':'adult','revision':'current'}
    corpus=[{'id':'xray','text':'рентгенография грудной клетки','topic':'C03','scope':'adult','revision':'current'},
            {'id':'codes','text':'код диагноза выписка','topic':'C05','scope':'adult','revision':'current'}]
    assert rank_bm25(query,corpus)==['xray','codes']
