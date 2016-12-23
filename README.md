# expolly
"ヴァル研究所 Advent Calendar 2016" day 23 sample source

## Overview
- "ヴァル研究所 Advent Calendar 2016" day 23 sample source.
- Please check the blog for details !
	- http://uchimanajet7.hatenablog.com/entry/2016/12/23/121918
- Also see other advent calendar articles.
	- http://qiita.com/advent-calendar/2016/val

## How to use
- `Required` 駅すぱあとWebサービス
	- If there is no such data it can not get the original data.
- Use `AWS Lambda` and `Amazon API Gateway`
	- You need an Amazon Web Services account.
- Use `Python Serverless Microframework for AWS (chalice)`
    - https://github.com/awslabs/chalice
	- required python

## Usage
1. Install `chalice`.
1. Clone this repository.
1. Refer to the `sample_policy.json` and make the settings. (It should be copied and moved as it is)　
1. Deploy your AWS. (with option `--no-autogen-policy`)　
1. Set Slack `Outgoing Webhooks`

