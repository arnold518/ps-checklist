# ps-checklist

## Adding new contest data

- [Google form link](https://docs.google.com/forms/d/1L0unHXDweAP_FRDslBt7Lk0XfOaB3ilCY4XCpBILSUY/edit)
- [Google form link (short)](https://forms.gle/5ac8SbgHhPsKxc8v5)
- [Google apps script link](https://script.google.com/home/projects/1usNeZ7eg12sNiNZzx99hO4er6qxYIO3z2G86HsLfQDfJAa7lu_-OfJf3/executions)
- [Google form response spreadsheet link](https://docs.google.com/spreadsheets/d/1peQ86F_bLdb1XUnBD-CntcW9_oq2HR2Og1beCNvbQvE/edit?resourcekey&usp=forms_web_b&urp=linked#gid=1471396257)

Data from google form is updated in [`problemlists/contestlist.json`](problemlists/contestlist.json), in branch `data`.
New data can be identified with `null` id.

1. Merge branch `data` to active deployed branch.
2. Run `cd crawler && python fetchContest.py` to get data for each contests with `null` id in [`problemlists/contestlist.json`](problemlists/contestlist.json).
3. The crawler will publish an `id` for each contest, insert it to `problemlists/categoryname/contesttree.json`.
4. Push to origin to deploy.