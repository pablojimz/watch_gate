        reportinfo = items[0].reportinfo()
        assert reportinfo[1] == 1

    @pytest.mark.skipif(
        sys.version_info < (3, 12), reason="requires Python 3.12 or later"
    )
    def test_fixture_doctest_skip_has_line_number(self, pytester: Pytester):
        p = pytester.makepyfile(
            test_fixture_doctest_skip="""
            import pytest

            @pytest.fixture
            def unavailable():
                '''
                >>> getfixture("unavailable")
                '''
                pytest.skip("unavailable")
            """
        )
        items, _reprec = pytester.inline_genitems(p, "--doctest-modules")
        assert items[0].reportinfo()[1] is not None

        result = pytester.runpytest(p, "--doctest-modules")
        assert "INTERNALERROR" not in result.stdout.str()
        result.assert_outcomes(skipped=1)

    def test_valid_setup_py(self, pytester: Pytester):
        """
        Test to make sure that pytest ignores valid setup.py files when ran
