                x.chmod(y)

    def test_copy_archiving(self, tmpdir):
        unicode_fn = "something-\342\200\223.txt"
        f = tmpdir.ensure("a", unicode_fn)
        a = f.dirpath()
        oldmode = f.stat().mode
