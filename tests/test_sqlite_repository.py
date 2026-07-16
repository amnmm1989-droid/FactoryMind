from repositories.sqlite_repository import SQLiteRepository


def test_months_exist():
    repo = SQLiteRepository()

    months = repo.get_months()

    assert len(months) == 44
    

def test_products_exist():
    repo = SQLiteRepository()

    products = repo.get_products()

    assert len(products) == 185
    
    
    
def test_product_data_length():
    repo = SQLiteRepository()

    product = repo.get_products()[0]

    values = repo.get_product_data(product)

    assert len(values) == 44    
    

def test_load_data():
    repo = SQLiteRepository()

    months, products = repo.load_data()

    assert len(months) == 44
    assert len(products) == 185
    
    
    
    
def test_metadata():
    repo = SQLiteRepository()

    meta = repo.get_metadata()

    assert meta["total_months"] == 44
    assert meta["total_products"] == 185    
    
