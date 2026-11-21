export const PROBLEM_STATES = ['Not Attempted', 'Attempted', 'Solved', 'Reviewed'];

export const NAV_ITEMS = [
    {id: 'icpc', name: 'ICPC'},
    {id: 'olympiad', name: 'Olympiad'},
    {id: 'platforms', name: 'Platforms'},
    {id: 'practice-records', name: 'Practice Records'}
];

export const PLATFORMS = [
    {id: 'cf', name: 'Codeforces', badge: 'CF', example: '2268 or https://codeforces.com/gym/106225'},
    {id: 'atcoder', name: 'AtCoder', badge: 'AC', example: 'agc078 or https://atcoder.jp/contests/agc078'}
];

export const PLATFORM_GROUPS = {
    cf: [
        {id: 'div1', name: 'Div. 1'},
        {id: 'div2', name: 'Div. 2'},
        {id: 'div1div2', name: 'Div. 1 + 2'},
        {id: 'div3', name: 'Div. 3'},
        {id: 'div4', name: 'Div. 4'},
        {id: 'gym', name: 'Gym'},
        {id: 'other', name: 'Other'}
    ],
    atcoder: [
        {id: 'abc', name: 'ABC'},
        {id: 'arc', name: 'ARC'},
        {id: 'agc', name: 'AGC'},
        {id: 'ahc', name: 'AHC'},
        {id: 'awc', name: 'AWC'},
        {id: 'other', name: 'Other'}
    ]
};

export const JUDGE_LINKS = [
    {id: 'boj', title: 'Baekjoon Online Judge', img: 'assets/icon/boj-icon.png'},
    {id: 'cf', title: 'Codeforces', img: 'assets/icon/cf-icon.png'},
    {id: 'qoj', title: 'QOJ', img: 'assets/icon/qoj-icon.png'},
    {id: 'atcoder', title: 'AtCoder', img: 'assets/icon/atcoder-icon.png'},
    {id: 'ojuz', title: 'oj.uz', img: 'assets/icon/ojuz-icon.svg'}
];
