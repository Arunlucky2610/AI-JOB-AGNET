"""Isolated JobSpy search process: bounded lifetime, no applicant personal data."""
import asyncio, json, os, sys, re

async def search(criteria):
    process=await asyncio.create_subprocess_exec(sys.executable,'-m','backend.jobspy_discovery',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        stdout,stderr=await asyncio.wait_for(process.communicate(json.dumps(criteria).encode()),timeout=80)
        if process.returncode:raise RuntimeError('JobSpy search process failed')
        result=json.loads(stdout)
        result['upstream_errors']=bool(re.search(r'ERROR|request failed|status code [45]\d\d',stderr.decode(errors='replace')))
        return result
    except BaseException:
        if process.returncode is None:
            process.kill();await process.wait()
        raise

def scrape(criteria):
    from jobspy import scrape_jobs
    sites=['google']
    if criteria['country'].strip().casefold()=='india':sites.append('naukri')
    proxies=json.loads(os.getenv('JOBSPY_PROXIES','[]'))
    level='entry level' if criteria.get('experience',0)<=1 else str(criteria['experience'])+' years experience'
    frame=scrape_jobs(site_name=sites,search_term=criteria['role'],google_search_term=f"{criteria['role']} jobs near {criteria['location']}, {criteria['country']} {level}",location=criteria['location']+', '+criteria['country'],country_indeed=criteria['country'].strip(),results_wanted=15,verbose=0,proxies=proxies or None)
    columns=[key for key in ['site','title','company','job_url','job_url_direct','company_url','location','description','experience_range'] if key in frame.columns]
    return {'sites':sites,'rows':json.loads(frame[columns].head(30).to_json(orient='records'))}

if __name__=='__main__':
    # Upstream stdout is redirected so only our bounded JSON result reaches the parent.
    import contextlib
    criteria=json.loads(sys.stdin.read())
    with contextlib.redirect_stdout(sys.stderr):result=scrape(criteria)
    sys.stdout.write(json.dumps(result))
