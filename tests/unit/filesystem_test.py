def test_list_only_directories(services_filesystem):
    regular_file = services_filesystem.root / "regular_file.txt"
    regular_file.touch()
    assert services_filesystem.list() == []
