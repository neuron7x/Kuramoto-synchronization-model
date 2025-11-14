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
    const pull_number = github.context.payload.pull_request.number;

    // Get changed files
    const { data: files } = await octokit.rest.pulls.listFiles({
      owner,
      repo,
      pull_number,
    });

    // Read CODEOWNERS content (should be set by previous step)
    const codeownersContent = process.env.CODEOWNERS_CONTENT || '';
    
    if (!codeownersContent) {
      core.info('No CODEOWNERS content available');
      core.setOutput('has_owners', 'false');
      core.setOutput('covered', '0');
      core.setOutput('uncovered', files.length.toString());
      core.setOutput('coverage_percent', '0');
      core.setOutput('uncovered_files', files.map(f => f.filename).join(','));
      return;
    }

    // Parse CODEOWNERS
    const ownersMap = {};
    codeownersContent.split('\n').forEach(line => {
      line = line.trim();
      if (line && !line.startsWith('#')) {
        const parts = line.split(/\s+/);
        if (parts.length >= 2) {
          ownersMap[parts[0]] = parts.slice(1);
        }
      }
    });

    // Check coverage
    let covered = 0;
    let uncovered = 0;
    const uncoveredFiles = [];

    files.forEach(file => {
      let hasCoverage = false;
      for (const [pattern, owners] of Object.entries(ownersMap)) {
        if (pattern === '*' || file.filename.includes(pattern.replace('*', ''))) {
          hasCoverage = true;
          break;
        }
      }

      if (hasCoverage) {
        covered++;
      } else {
        uncovered++;
        uncoveredFiles.push(file.filename);
      }
    });

    const totalFiles = files.length;
    const coveragePercent = totalFiles > 0 ? ((covered / totalFiles) * 100).toFixed(1) : '100';

    core.setOutput('has_owners', 'true');
    core.setOutput('covered', covered.toString());
    core.setOutput('uncovered', uncovered.toString());
    core.setOutput('coverage_percent', coveragePercent);
    core.setOutput('uncovered_files', uncoveredFiles.join(','));

    core.info(`Code ownership coverage: ${coveragePercent}%`);
    core.info(`Covered: ${covered}, Uncovered: ${uncovered}`);
  } catch (err) {
    core.error(`Error checking ownership: ${err && err.message}`);
    core.setFailed(err && err.message ? err.message : 'Unknown error checking ownership');
  }
})();
