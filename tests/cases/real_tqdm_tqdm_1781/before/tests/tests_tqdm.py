    assert format_meter(231, 1000, 392) == (" 23%|" + unich(0x2588) * 2 + unich(0x258e) +
                                            "       | 231/1000 [06:32<21:44,  1.70s/it]")
    assert format_meter(10000, 1000, 13) == "10000it [00:13, 769.23it/s]"
    assert format_meter(231, 1000, 392, ncols=56, ascii=True) == " 23%|" + '#' * 3 + '6' + (
        "            | 231/1000 [06:32<21:44,  1.70s/it]")
    assert format_meter(100000, 1000, 13, unit_scale=True,
