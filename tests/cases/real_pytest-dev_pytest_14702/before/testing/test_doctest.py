        reportinfo = items[0].reportinfo()
        assert reportinfo[1] == 1

    def test_valid_setup_py(self, pytester: Pytester):
        """
        Test to make sure that pytest ignores valid setup.py files when ran
