/**
 * Tests for safeReadCodeowners function
 * Validates safe base64 decoding with proper error handling
 */

describe('safeReadCodeowners', () => {
  let mockCore;
  let mockOctokit;
  let safeReadCodeowners;

  beforeEach(() => {
    // Mock @actions/core
    mockCore = {
      info: jest.fn(),
      warning: jest.fn(),
      setOutput: jest.fn(),
    };
    global.core = mockCore;

    // Define the function (in real workflow, this is inline)
    safeReadCodeowners = async function(octokit, owner, repo, ref) {
      try {
        const res = await octokit.rest.repos.getContent({
          owner,
          repo,
          path: 'CODEOWNERS',
          ref
        });
        
        const base64 = (res && res.data && res.data.content) ? res.data.content : null;
        
        if (!base64 || typeof base64 !== 'string') {
          mockCore.info('CODEOWNERS not present or content invalid');
          mockCore.setOutput('has_owners', 'false');
          return null;
        }
        
        const compact = base64.replace(/\r?\n/g, '').trim();
        
        if (!/^[A-Za-z0-9+\/=]+$/.test(compact)) {
          mockCore.warning('CODEOWNERS content is not valid base64; abort decode.');
          mockCore.setOutput('has_owners', 'false');
          return null;
        }
        
        let decoded;
        try {
          decoded = Buffer.from(compact, 'base64').toString('utf8');
        } catch (err) {
          mockCore.warning('Failed to decode CODEOWNERS base64: ' + err.message);
          mockCore.setOutput('has_owners', 'false');
          return null;
        }
        
        decoded = decoded.replace(/^\uFEFF/, '');
        
        mockCore.setOutput('has_owners', 'true');
        mockCore.info(`CODEOWNERS length: ${decoded.length}`);
        return decoded;
      } catch (err) {
        mockCore.info(`Could not read CODEOWNERS: ${err && err.message ? err.message : String(err)}`);
        mockCore.setOutput('has_owners', 'false');
        return null;
      }
    };
  });

  test('should return null when file not found', async () => {
    mockOctokit = {
      rest: {
        repos: {
          getContent: jest.fn().mockRejectedValue(new Error('Not Found'))
        }
      }
    };

    const result = await safeReadCodeowners(mockOctokit, 'owner', 'repo', 'main');
    
    expect(result).toBeNull();
    expect(mockCore.setOutput).toHaveBeenCalledWith('has_owners', 'false');
    expect(mockCore.info).toHaveBeenCalledWith(expect.stringContaining('Could not read CODEOWNERS'));
  });

  test('should return null when content is empty', async () => {
    mockOctokit = {
      rest: {
        repos: {
          getContent: jest.fn().mockResolvedValue({
            data: { content: '' }
          })
        }
      }
    };

    const result = await safeReadCodeowners(mockOctokit, 'owner', 'repo', 'main');
    
    expect(result).toBeNull();
    expect(mockCore.setOutput).toHaveBeenCalledWith('has_owners', 'false');
  });

  test('should return null when base64 is invalid', async () => {
    mockOctokit = {
      rest: {
        repos: {
          getContent: jest.fn().mockResolvedValue({
            data: { content: 'invalid!@#$%base64' }
          })
        }
      }
    };

    const result = await safeReadCodeowners(mockOctokit, 'owner', 'repo', 'main');
    
    expect(result).toBeNull();
    expect(mockCore.setOutput).toHaveBeenCalledWith('has_owners', 'false');
    expect(mockCore.warning).toHaveBeenCalledWith(expect.stringContaining('not valid base64'));
  });

  test('should decode valid base64 content', async () => {
    const testContent = '* @owner1 @owner2';
    const base64Content = Buffer.from(testContent, 'utf8').toString('base64');
    
    mockOctokit = {
      rest: {
        repos: {
          getContent: jest.fn().mockResolvedValue({
            data: { content: base64Content }
          })
        }
      }
    };

    const result = await safeReadCodeowners(mockOctokit, 'owner', 'repo', 'main');
    
    expect(result).toBe(testContent);
    expect(mockCore.setOutput).toHaveBeenCalledWith('has_owners', 'true');
    expect(mockCore.info).toHaveBeenCalledWith(`CODEOWNERS length: ${testContent.length}`);
  });

  test('should remove BOM if present', async () => {
    const testContent = '\uFEFF* @owner1';
    const base64Content = Buffer.from(testContent, 'utf8').toString('base64');
    
    mockOctokit = {
      rest: {
        repos: {
          getContent: jest.fn().mockResolvedValue({
            data: { content: base64Content }
          })
        }
      }
    };

    const result = await safeReadCodeowners(mockOctokit, 'owner', 'repo', 'main');
    
    expect(result).toBe('* @owner1');
    expect(result).not.toContain('\uFEFF');
  });

  test('should handle base64 with newlines', async () => {
    const testContent = '* @owner1 @owner2';
    const base64Content = Buffer.from(testContent, 'utf8').toString('base64');
    const base64WithNewlines = base64Content.match(/.{1,64}/g).join('\n');
    
    mockOctokit = {
      rest: {
        repos: {
          getContent: jest.fn().mockResolvedValue({
            data: { content: base64WithNewlines }
          })
        }
      }
    };

    const result = await safeReadCodeowners(mockOctokit, 'owner', 'repo', 'main');
    
    expect(result).toBe(testContent);
  });
});
