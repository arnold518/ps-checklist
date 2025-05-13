# ps-checklist

## Setting up venv for fetContest.py

Must set up environment in Windows.

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

cd crawler && python fetchContest.py
```

## Adding new contest data

- [Raw contest data spreadsheet link](https://docs.google.com/spreadsheets/d/12M6sfXrC7eOhgHuu3Kk0ZpbAfHQ2h8ZUEr60nTVifiM/edit?gid=0#gid=0)
- [Full contestlist spreadsheet link](https://docs.google.com/spreadsheets/d/1Ld3PMgmA2tEgRFT0fp0Yt9uhpOKUldWKtaIOkp0eG3Q/edit?gid=0#gid=0)

Data from google form is updated in [`problemlists/contestlist.json`](problemlists/contestlist.json), in branch `data`.
New data can be identified with `null` id.

1. Run `cd crawler && python fetchContest.py` to get data for each contests with `null` id in [`problemlists/contestlist.json`](problemlists/contestlist.json).
2. The crawler will publish an `id` for each contest, and also it will insert it to `problemlists/categoryname/contesttree.json`.
3. Merge branch `data` to active deployed branch.
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