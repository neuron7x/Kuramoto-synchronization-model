#!/usr/bin/env node
'use strict';
const core = require('@actions/core');
const github = require('@actions/github');

(async function main() {
  try {
    const token = process.env.GITHUB_TOKEN;
    if (!token) throw new Error('GITHUB_TOKEN not provided');

    const octokit = github.getOctokit(token);
    const { owner, repo } = github.context.repo;
    const ref = github.context.payload?.pull_request?.base?.ref ||
                (github.context.ref || '').replace(/^refs\/heads\//, '');
    const path = 'CODEOWNERS';

    const resp = await octokit.rest.repos.getContent({ owner, repo, path, ref });

    // support both resp.data.content and resp.content shapes
    const base64 = resp?.data?.content || resp?.content || null;
    if (!base64) {
      core.info('CODEOWNERS not found or empty');
      core.setOutput('has_owners', 'false');
      process.exit(0);
    }

    // decode safely and strip BOM if present
    const content = Buffer.from(base64, 'base64').toString('utf8').replace(/^\uFEFF/, '');
    core.setOutput('has_owners', 'true');
    core.setOutput('codeowners', content);
    core.info('CODEOWNERS read successfully');
  } catch (err) {
    if (err && err.status === 404) {
      core.info('CODEOWNERS not found (404)');
      core.setOutput('has_owners', 'false');
      process.exit(0);
    }
    core.error(`Error reading CODEOWNERS: ${err && err.message}`);
    core.setFailed(err && err.message ? err.message : 'Unknown error reading CODEOWNERS');
  }
})();
