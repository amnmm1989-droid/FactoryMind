import statistics
import time

from repositories.json_repository import JsonRepository
from repositories.sqlite_repository import SQLiteRepository


def benchmark(repo, loops=20):
    results = []

    for _ in range(loops):
        start = time.perf_counter()
        repo.load_data()
        results.append(time.perf_counter() - start)

    return statistics.mean(results), statistics.stdev(results)


json_repo = JsonRepository()
sqlite_repo = SQLiteRepository()

json_avg, json_std = benchmark(json_repo)
sqlite_avg, sqlite_std = benchmark(sqlite_repo)

print()

print("JSON")
print(f"Average : {json_avg:.6f}s")
print(f"Std Dev : {json_std:.6f}s")

print()

print("SQLite")
print(f"Average : {sqlite_avg:.6f}s")
print(f"Std Dev : {sqlite_std:.6f}s")

print()

print(f"Speedup : {json_avg/sqlite_avg:.2f}x")
