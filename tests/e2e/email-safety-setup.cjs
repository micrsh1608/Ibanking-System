const {request}=require('@playwright/test');
module.exports=async config=>{
    const api=await request.newContext({baseURL:config.projects[0].use.baseURL});
    try{
        const response=await api.get('/app-config');
        if(!response.ok()||(await response.json()).email_delivery!=='mailpit') throw new Error('Browser acceptance requires Mailpit for synthetic email. Run: python -m tests.integration.release_acceptance --cached-build --full-checks');
    }finally{await api.dispose();}
};
