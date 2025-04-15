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

## Contest Tree Rules

1. All nodes in contest tree is either a `contest` or a `directory`.
2. Each `directory` must have `contests` or `subdirectories` as children nodes, not both.

### ICPC

[problemlists/icpc/contesttree.json](problemlists/icpc/contesttree.json)

1. Each "region" (`directory`) has a "region finals (championship)" (`contest`) and "regionals" (`subdirectory`).
The "regionals" (`subdirectory`) has a list of "subregion" (`directory`), which continues recursively.

    ```
    (example)

    ["Asia Pacific"
        ,["Asia Pacific Championship"

        ]
        ,["Regionals"
            ,["Korea"

            ]
            ,["Japan"

            ]
            ,["Indonesia (Jakarta)"

            ]
        ]
    ]
    ```
2. If a `directory` has only one `subdirectory` as its child node, it is recommended that the `directory` is omitted for simplicity.
When more `subdirectory` is added in the future, the omitted `directory` must be shown again.

    ```
    (not recommended)

    ["Central Europe"
        ,["Central European Regional Contest (CERC)"

        ]
        ,["Regionals"
            ,["Poland Collegiate Programming Contest (AMPPZ)"

            ]
        ]
        
    ]

    ["Latin America"
        ,["Latin America Championship"

        ]
        ,["Regionals"
            ,["Latin America Regional Contest"

            ]
        ]
    ]
    ```

    ```
    (recommended)

    ["Central Europe"
        ,["Central European Regional Contest (CERC)"

        ]
        ,["Poland Collegiate Programming Contest (AMPPZ)"

        ]
    ]

    ["Latin America"
        ,["Latin America Championship"

        ]
        ,["Latin America Regional Contest"

        ]
    ]
    ```