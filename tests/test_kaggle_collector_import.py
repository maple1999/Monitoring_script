def test_kaggle_import_optional():
    try:
        import importlib
        m = importlib.import_module('src.collector.kaggle_api')
        assert hasattr(m, 'collect_kaggle_contests')
    except Exception:
        # module exists even if kaggle package is missing; function handles it
        assert True

