def test_harness_package_declares_version():
    import harness

    assert harness.__version__ == "0.1.0"
