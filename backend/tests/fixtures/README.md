# Test Fixtures

## NGX Daily Official List PDFs

Place real PDF fixtures here for end-to-end parser testing.

### How to get a fixture

1. Download a PDF from:
   ```
   https://doclib.ngxgroup.com/DownloadsContent/Daily%20Official%20List%20-%20Equities%20for%2002-02-2026.pdf
   ```
   (Adjust the date as needed — format is DD-MM-YYYY)

2. Save it as:
   ```
   tests/fixtures/ngx_daily_list_YYYY-MM-DD.pdf
   ```

3. The test `test_parse_real_fixture` in `test_ngx_official_list.py`
   will auto-detect any `.pdf` file in this directory and run the
   parser against it.

### What the tests check with a real fixture

- Header detection succeeds
- At least 10 equity rows parsed
- Known symbols (DANGCEM, GTCO, MTNN) present with valid close prices
- No NaN/None close prices on parsed rows
