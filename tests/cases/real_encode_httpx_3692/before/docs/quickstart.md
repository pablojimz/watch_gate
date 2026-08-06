of items for the file value:

```pycon
>>> with open('report.xls', 'rb') report_file:
...     files = {'upload-file': ('report.xls', report_file, 'application/vnd.ms-excel')}
...     r = httpx.post("https://httpbin.org/post", files=files)
>>> print(r.text)
