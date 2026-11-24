# sandbox-public

Scripts, GitHub Actions and small examples I've built for my own projects and
usually written about on [coreydaley.dev](https://coreydaley.dev). Each folder
stands on its own with a README: copy it, set a few variables, adapt it.
They're shared as-is, not maintained as packages.

Examples are grouped by what they plug into.

| Example | What it does |
|---|---|
| [`hugo/indexnow`](hugo/indexnow/) | Submits only new and changed pages to IndexNow (Bing and others) after each deploy, ignoring sidebar churn. |
| [`hugo/social-post`](hugo/social-post/) | Shares new Hugo blog posts to Bluesky and LinkedIn from a GitHub Action, using text approved at writing time. |

## Using an example

Each README lists its files, setup steps and caveats, including what hasn't
been tested. Tests run without network access or credentials:

```bash
make test
```

## Contributing

Issues and suggestions are welcome. Each example matches how I use it, so a
change that makes one more general may not get merged.

## License

[MIT](LICENSE)
