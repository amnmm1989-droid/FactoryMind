def test_months_exist(repo):
    months = repo.get_months()

    assert len(months) == 44


def test_products_exist(repo):
    products = repo.get_products()

    assert len(products) == 185


def test_product_data_length(repo):
    product = repo.get_products()[0]

    values = repo.get_product_data(product)

    assert len(values) == 44


def test_load_data(repo):
    months, products = repo.load_data()

    assert len(months) == 44
    assert len(products) == 185


def test_metadata(repo):
    meta = repo.get_metadata()

    assert meta["total_months"] == 44
    assert meta["total_products"] == 185
