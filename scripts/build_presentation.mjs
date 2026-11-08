/** Build editable technical slides using the Codex bundled Artifact Tool.
 * Optional authoring tool; not required to start or run the application.
 * Set IBANKING_ARTIFACT_MODULE, IBANKING_PRESENTATION_SKILL, IBANKING_BUILD_PYTHON.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=process.cwd();
const modulePath=process.env.IBANKING_ARTIFACT_MODULE;
if(!modulePath) throw new Error('Set IBANKING_ARTIFACT_MODULE to bundled artifact_tool.mjs');
const {Presentation,PresentationFile}=await import(pathToFileURL(modulePath).href);
const team=JSON.parse(await fs.readFile('docs/team.json','utf8'));
const result=JSON.parse(await fs.readFile('artifacts/release-acceptance-latest.json','utf8'));
if(result.status!=='PASS') throw new Error('Release acceptance must pass before publication');
const tmp=path.join(root,'artifacts/submission-final-build');
const out=path.join(root,'submission');
const diagrams=path.join(root,'docs/diagrams/exported');
for(const dir of [tmp,out,diagrams]) await fs.mkdir(dir,{recursive:true});
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:'#16352F',green:'#087F69',muted:'#526A64',pale:'#EFF6F3',line:'#B8CCC4',white:'#FFFFFF'};
const font='Arial';
function text(s,content,x,y,w,h,size=26,bold=false,color=C.ink,align='left'){
 const o=s.shapes.add({geometry:'textbox',name:content.slice(0,55),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 o.text=content; o.text.style={typeface:font,fontSize:size,bold,color,alignment:align,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:0}; return o;
}
function box(s,content,x,y,w,h,{size=25,fill=C.pale,geometry='rect',bold=false}={}){
 const o=s.shapes.add({geometry,name:content.split('\n')[0],position:{left:x,top:y,width:w,height:h},fill,line:{fill:C.line,width:1.3}});
 o.text=content; o.text.style={typeface:font,fontSize:size,bold,color:C.ink,alignment:'center',verticalAlignment:'middle',autoFit:'none',wrap:'square',insets:12}; return o;
}
function link(s,a,b,from='right',to='left',arrow=true){return s.shapes.connect(a,b,{kind:'straight',fromSide:from,toSide:to,line:{fill:C.green,width:2},...(arrow?{tail:{type:'triangle',width:'med',length:'med'}}:{})});}
function slide(title,note=''){
 const s=p.slides.add(); s.background.fill=C.white;
 text(s,title,64,44,1152,p.slides.items.length===1?100:66,p.slides.items.length===1?56:42,true);
 text(s,'NHÓM 12  /  IBANKING',64,678,550,20,15,false,C.muted);
 text(s,String(p.slides.items.length).padStart(2,'0'),1164,678,50,20,15,false,C.muted,'right');
 s.speakerNotes.text=note; return s;
}
function lines(s,items,x=70,y=160,w=1120,gap=93,size=28){items.forEach((t,i)=>text(s,t,x,y+i*gap,w,gap-12,size));}
function entity(s,name,fields,x,y,w=480,h=185,size=23){
 const b=box(s,'',x,y,w,h,{fill:C.white});
 box(s,name,x,y,w,48,{fill:C.pale,size:25,bold:true});
 text(s,fields.join('\n'),x+16,y+60,w-32,h-68,size); return b;
}
const diagramSlides=[];
let s=slide('Thanh toán học phí qua iBanking','Báo cáo giữa kỳ. Thông tin nhóm do người dùng cung cấp. MSSV giữ nguyên 524H009; hai thành viên sẽ điền sau.');
text(s,team.course,68,160,1144,50,32,false,C.green);
text(s,`${team.group}  ·  Giảng viên: ${team.lecturer}`,68,228,1144,46,27);
text(s,team.members.map((m,i)=>`${i+1}. ${m.name}  —  ${m.student_id}`).join('\n'),68,326,1144,170,27);
text(s,'FastAPI  /  SQL Server  /  Docker',68,565,1144,45,29,true);

s=slide('Phạm vi và Use Case','Nguồn: docs/architecture.md; docs/diagrams/use-cases.puml. Các chức năng có điều kiện JWT. Đăng xuất xóa token trên trình duyệt, chưa thu hồi token trung tâm.');
box(s,'',300,135,700,495,{fill:'none'});
text(s,'Phân hệ đóng học phí',330,146,610,30,24,true);
const actor=box(s,'«actor»\nNgười trả',65,330,185,105,{fill:C.white,size:26});
const mail=box(s,'«actor»\nSMTP',1040,345,174,105,{fill:C.white,size:25});
const ucs=['Đăng nhập','Hồ sơ và xác minh email','Tra toàn bộ công nợ MSSV','Đồng ý điều khoản và OTP','Thanh toán toàn bộ công nợ','Kết quả, lịch sử và biên nhận','Đăng xuất'];
ucs.forEach((v,i)=>{const uc=box(s,v,390,185+i*60,520,50,{geometry:'ellipse',fill:C.pale,size:22});link(s,actor,uc,'right','left',false);if([1,3,5].includes(i))link(s,uc,mail,'right','left',false);});
diagramSlides.push(['use-cases',s]);

s=slide('Ba service, ba miền dữ liệu','Nguồn: compose.yaml; docs/architecture.md. Các DB cùng một SQL Server ở bản demo. Gateway chỉ chuyển tiếp public API; nội bộ dùng X-Internal-Key. Worker nằm trong Payment.');
const web=box(s,'Web UI\nJWT · cùng origin',64,233,230,110);
const acc=box(s,'Account :8001\nJWT · Gateway · Ledger\nXác minh email',375,155,340,110,{size:23});
const pay=box(s,'Payment :8002\nOTP · Saga · Recovery · Outbox',375,350,340,116);
const tui=box(s,'Tuition :8003\nHóa đơn · Reservation',856,350,350,116);
const adb=box(s,'account_db',856,165,350,80,{fill:C.white});
const pdb=box(s,'payment_db',375,545,340,70,{fill:C.white});
const tdb=box(s,'tuition_db',856,545,350,70,{fill:C.white});
const smtp=box(s,'Mailpit / SMTP',64,536,230,80,{fill:C.white});
link(s,web,acc);link(s,acc,adb);link(s,acc,pay,'bottom','top');link(s,pay,acc,'top','bottom');
link(s,acc,tui,'right','top');text(s,'Gateway / JWT',924,255,280,30,21,false,C.muted);
link(s,pay,tui);text(s,'REST nội bộ',720,315,160,34,22,false,C.muted);
link(s,pay,pdb,'bottom','top');link(s,tui,tdb,'bottom','top');link(s,pay,smtp,'left','right');
link(s,acc,smtp,'left','top');text(s,'Xác minh email',65,385,210,30,21,false,C.muted);
text(s,'Một SQL Server cho demo; không có FK hoặc truy vấn bảng xuyên service.',65,635,1140,29,23,false,C.muted);
diagramSlides.push(['microservices',s]);

s=slide('ERD — Account','Nguồn chính xác: services/account/models.py. PK/FK là khóa vật lý cùng DB. Các ô liệt kê thuộc tính cốt lõi; schema đầy đủ trong model và migration.');
const us=entity(s,'users',['PK id · UQ username · password_hash','full_name · email · phone · identity_number','email_verified_at · pending_email','email_challenge_id · email_code_hash','email_code_expires_at · email_code_attempts','is_active · created_at'],64,150,490,255,21);
const ac=entity(s,'accounts',['PK id · FK/UQ user_id → users','UQ account_number','balance NUMERIC(18,2) ≥ 0','status ACTIVE / LOCKED'],728,150,490,205);
const en=entity(s,'account_entries',['PK id · FK account_id → accounts','payment_id · entry_type · amount','UQ(payment_id, entry_type)','entry_type DEBIT / REFUND'],64,423,490,205);
const can=entity(s,'account_cancellations',['PK payment_id','FK account_id → accounts','payer_user_id · amount > 0','Hàng rào hủy vĩnh viễn'],728,423,490,205);
link(s,us,ac,'right','left',false);text(s,'1 — 0..1',565,224,156,35,24);
link(s,ac,en,'bottom','top',false);link(s,ac,can,'bottom','top',false);
text(s,'1 — 0..*',575,355,135,30,22);text(s,'1 — 0..* dấu hủy',992,374,220,35,23);
diagramSlides.push(['erd-account',s]);

s=slide('ERD — Tuition','Nguồn: services/tuition/models.py. Một sinh viên có nhiều hóa đơn; một reservation chứa nhiều item. invoice_id trong item có FK đến tuition_invoices; đều trong tuition_db. paid/reserved_payment_id là tham chiếu logic UUID.');
const stu=entity(s,'students',['PK id · UQ mssv','full_name'],64,155,490,155);
const inv=entity(s,'tuition_invoices',['PK id · FK student_id → students','semester · amount_due · version','status · reserved/paid_payment_id','UQ(student_id, semester)'],728,155,490,205);
const res=entity(s,'tuition_reservations',['PK payment_id · request_hash','mssv · total_amount','status RESERVED / PAID / RELEASED'],64,435,490,170);
const ri=entity(s,'tuition_reservation_items',['PK id · FK payment_id → reservations','FK invoice_id → tuition_invoices','amount NUMERIC(18,2)','UQ(payment_id, invoice_id)'],728,435,490,205);
link(s,stu,inv,'right','left',false);text(s,'1 — 0..*',564,210,155,36,24);
link(s,res,ri,'right','left',false);text(s,'1 — 0..*',564,474,155,36,24);
link(s,inv,ri,'bottom','top',false);text(s,'1 — 0..*',980,380,200,34,23);
diagramSlides.push(['erd-tuition',s]);

s=slide('ERD — Payment','Nguồn: services/payment/models/payment.py. payer_user_id/account_id/invoice_id là tham chiếu logic qua API, không là FK sang Account/Tuition. schema_revisions thuộc hạ tầng và lược khỏi sơ đồ.');
const pm=entity(s,'payments',['PK payment_id UUID · UQ transaction_code','request_hash · payer/account/MSSV snapshot','total_amount · status · phase · retry_count','terms_version · terms_accepted_at','OTP HMAC · fingerprint · challenge · hạn','created_at · completed_at'],330,140,620,245,21);
const pi=entity(s,'payment_items',['PK id · FK payment_id → payments','invoice_id · invoice_version','semester · amount','UQ(payment_id, invoice_id)'],64,448,490,190);
const ob=entity(s,'email_outbox',['PK id · FK payment_id → payments','event_type · recipient · body','status · attempts · next_attempt_at','UQ(payment_id, event_type)'],728,448,490,190);
link(s,pm,pi,'bottom','top',false);link(s,pm,ob,'bottom','top',false);
text(s,'1 — 1..* khi tạo payment',69,390,490,34,23);text(s,'1 — 0..*',1005,398,200,34,23);
diagramSlides.push(['erd-payment',s]);

s=slide('Luồng thanh toán và điểm commit','Nguồn: services/payment/coordinator.py; services/payment/outbox.py. HTTP giữa service nằm ngoài transaction SQL. OTP_VERIFY đã hoàn thành trước process. Khi finalize PAID, lưu SUCCEEDED + outbox cùng transaction Payment.');
const xs=[145,410,675,940,1170]; const actors=['Web','Payment','Tuition','Account','SMTP'];
actors.forEach((v,i)=>{box(s,v,xs[i]-80,140,160,55,{size:24});const a=text(s,'',xs[i],200,1,1);const b=text(s,'',xs[i],615,1,1);link(s,a,b,'bottom','top',false);});
const events=[[0,1,'1. process · UUID'],[1,2,'2. reserve toàn bộ nhóm'],[1,3,'3. debit đúng tổng'],[1,2,'4. finalize → PAID'],[1,1,'5. commit SUCCEEDED + outbox'],[1,0,'6. kết quả / polling'],[1,4,'7. worker gửi biên nhận']];
events.forEach(([a,b,label],i)=>{const y=225+i*54;if(a===b){const labelShape=text(s,label,435,y,730,35,24,true,C.green);labelShape.fill=C.white;}else{const left=Math.min(xs[a],xs[b]),right=Math.max(xs[a],xs[b]);text(s,label,left+12,y-8,right-left-15,34,23);const aa=text(s,'',xs[a],y+27,1,1),bb=text(s,'',xs[b],y+27,1,1);link(s,aa,bb,'right','left');}});
text(s,'Timeout không kết luận thất bại: lưu phase, đối soát và thử lại cùng UUID.',65,631,1150,32,24,true,C.green);
diagramSlides.push(['payment-sequence',s]);

s=slide('REST API có hợp đồng rõ ràng','Nguồn đầy đủ: docs/api.md, OpenAPI tại :8001/:8002/:8003/openapi.json. Bảng rút gọn; prefix /api/v1/payments ở Payment. 503 khi chưa tiếp cận DB; 202 khi cần đối soát.');
const values=[['Thao tác','Method / URI','Kết quả chính'],['Đăng nhập','POST /auth/login','200 JWT / 401'],['Tra học phí','GET /api/v1/tuition/{mssv}','200 / 404'],['Tạo snapshot','POST /api/v1/payments','201 / 200 lặp / 409'],['Xác minh OTP','POST .../{id}/verify-otp','200 / 400 / 429'],['Thanh toán','POST .../{id}/process','200 / 202 / 409'],['Tra kết quả','GET .../{id}','200 / 404 sai chủ']];
const t=s.tables.add({rows:values.length,columns:3,left:64,top:155,width:1152,height:416,columnWidths:[240,600,312],values});
t.borders.assign({fill:C.line,width:1,style:'solid'});
for(let r=0;r<values.length;r++)for(let c=0;c<3;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.ink:(r%2?C.white:C.pale);cell.text.style={typeface:font,fontSize:23,bold:r===0,color:r===0?C.white:C.ink,insets:10,verticalAlignment:'middle'};}
text(s,'Client gửi MSSV, ALL_UNPAID, terms_accepted=true và Idempotency-Key UUID.',65,598,1145,55,25);

s=slide('Nhất quán khi giao dịch đồng thời','Nguồn: services/account/internal_routes.py; services/tuition/internal_routes.py; shared/locking.py; tests/integration/backend_acceptance.py. Khóa SQL theo tài khoản/hóa đơn và UUID; guard session dùng engine NullPool riêng để không chiếm pool ORM.');
lines(s,['Một tài khoản: khóa dòng và kiểm tra số dư trong cùng transaction.','Một hóa đơn: giữ cả nhóm theo thứ tự ID; không commit một phần.','Một UUID: cùng dữ liệu trả kết quả cũ; khác dữ liệu trả 409.','Lỗi chưa rõ kết quả: đối soát bền vững; hủy có hàng rào chặn request đến muộn.','Guard điều phối dùng kết nối riêng; transaction dữ liệu luôn ngắn.'],70,155,1140,92,27);

s=slide('OTP và xác minh email','Nguồn: shared/mailer.py; services/account/email_verification.py; services/payment/routes.py; services/payment/outbox.py; docs/api.md. Mã xác minh email và OTP thanh toán là hai mục đích riêng; email mới chỉ dùng sau khi có bằng chứng sở hữu. SMTP có thể nhận thư trùng khi mất ACK.');
text(s,'OTP',66,160,490,55,36,true,C.green);
lines(s,['6 chữ số, hạn 5 phút, dùng một lần','Mã còn hiệu lực không trùng nhau','Tối đa 5 lần sai, resend sau 60 giây','HMAC gắn UUID, challenge, snapshot'],66,242,520,85,26);
text(s,'Email và biên nhận',690,160,520,55,36,true,C.green);
lines(s,['Email hồ sơ cần được xác minh trước','Đổi email cần nhập mã ở địa chỉ mới','Biên nhận ghi cùng SUCCEEDED','Outbox retry độc lập với trừ tiền'],690,242,520,85,26);

s=slide('Giao diện đi được toàn bộ luồng','Ảnh: artifacts/payment-history-desktop.png và artifacts/payment-success-mobile.png. Dữ liệu test hư cấu. Nguồn kiểm thử: artifacts/browser-acceptance.json; 26 bài Edge desktop/mobile. JWT và OTP chỉ giữ trong RAM.');
for(const [file,x,y,w,h] of [['artifacts/payment-history-desktop.png',64,165,850,450],['artifacts/payment-success-mobile.png',964,145,242,493]]){
 s.images.add({blob:new Uint8Array(await fs.readFile(file)),contentType:'image/png',alt:file,fit:'contain',position:{left:x,top:y,width:w,height:h}});
}

s=slide('Kết quả kiểm thử tải trên máy hiện tại',`Nguồn: artifacts/release/${result.run_id}/acceptance.json. ${result.load.payments} giao dịch, ${result.load.workers} request process đồng thời, ${result.load.invoices} hóa đơn. Thời gian dưới đây đo HTTP process lần đầu. Không suy ra SLA hay năng lực production từ một máy Docker.`);
text(s,`${result.load.payments}/${result.load.payments}`,68,168,450,100,76,true,C.green);
text(s,'giao dịch hoàn tất và đối chiếu đủ ba DB',68,283,510,100,28);
text(s,`${result.load.workers} request đồng thời`,690,176,520,60,36,true);
text(s,`p50: ${result.load.p50_seconds}s\np95: ${result.load.p95_seconds}s\nLâu nhất: ${result.load.max_seconds}s`,690,265,500,190,31);
text(s,'Mỗi UUID: một DEBIT, đúng tổng tiền, hai hóa đơn PAID và một outbox event.',68,490,1135,80,29);
text(s,'Đã sửa điểm nghẽn khi guard điều phối dùng chung pool ORM.',68,602,1135,40,25,false,C.muted);

s=slide('Thử lỗi và truy vết giao dịch',`Nguồn: artifacts/release/${result.run_id}/acceptance.json; artifacts/observability-acceptance.json; shared/observability.py. Fault proxy chỉ có trong compose.acceptance.yaml. Các thao tác Docker kill/disconnect chỉ áp dụng project ${result.project}. Correlation ID không phải full W3C distributed tracing.`);
lines(s,['Mất reply sau debit: chỉ một lần trừ tiền.','Mất reply sau finalize: giữ PAID, phục hồi SUCCEEDED.','Ngắt mạng: chờ đối soát, nối lại và hoàn tất.','SIGKILL Payment: tiếp tục từ phase đã lưu.','SIGKILL SQL giữa transaction: rollback và retry.'],70,160,1135,88,27);
text(s,'X-Request-ID xuyên ba service; log JSON dùng route mẫu, không ghi OTP/token.',70,615,1135,43,23,true,C.green);

s=slide('Chuẩn bị và trình diễn','Nguồn: start.ps1 -PrepareDemo -Detached; start.ps1; docs/demo-script.md; docs/final-acceptance.md. Chuẩn bị chỉ thêm công nợ, không thanh toán hoặc gửi email. Đăng nhập bằng tài khoản đã cấp và xác minh email trước. Các image cần tải mạng lần đầu.');
text(s,'.\\start.ps1 -PrepareDemo -Detached',68,160,1135,90,40,true,C.green);
lines(s,['1. Đăng nhập, dùng MSSV mới và xác nhận toàn bộ công nợ.','2. Nhập OTP, đối chiếu số dư, PAID, lịch sử và biên nhận.','3. Giải thích hai ca cạnh tranh, retry và mã truy vết REST.'],68,285,1135,92,27);
text(s,'Trước khi nộp: điền hai thành viên còn lại và phân công thực tế.',68,584,1135,65,26,true);

for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(tmp,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
}
for(const [name,s] of diagramSlides){const blob=await p.export({slide:s,format:'png',scale:1.5});await fs.writeFile(path.join(diagrams,name+'.png'),new Uint8Array(await blob.arrayBuffer()));}
const candidate=path.join(tmp,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
const skill=process.env.IBANKING_PRESENTATION_SKILL;
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const filename=process.env.IBANKING_DECK_NAME||'trinh-bay-ibanking-v3.pptx';
let referencePath=path.join(out,'trinh-bay-ibanking-v2.pptx');
try{await fs.access(referencePath);}catch{referencePath=path.join(out,'trinh-bay-ibanking-v3.pptx');}
const referenceSha256=createHash('sha256').update(await fs.readFile(referencePath)).digest('hex');
const exportDirectory=path.join(root,'artifacts/submission-final-export');await fs.mkdir(exportDirectory,{recursive:true});
const exportId=Date.now().toString();
const validatedPath=path.join(exportDirectory,exportId+'-'+filename);
const receiptPath=path.join(tmp,exportId+'-'+filename+'.validation.json');
const finalized=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:validatedPath,pythonExecutable:process.env.IBANKING_BUILD_PYTHON,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','8'],requiredNativeTableOwnerSlides:[8],fontPolicy:{basis:'reference',families:[font],referencePath,referenceSha256},verifyArtifactToolImport:true,receiptPath});
try{await fs.copyFile(path.join(out,filename),path.join(tmp,Date.now()+'-previous-'+filename));}catch(error){if(error.code!=='ENOENT')throw error;}
await fs.copyFile(validatedPath,path.join(out,filename));
await fs.writeFile(path.join(tmp,'latest-presentation.json'),JSON.stringify({receiptPath,output:path.join(out,filename),sha256:finalized.finalSha256,slides:p.slides.items.length}));
console.log(JSON.stringify({slides:p.slides.items.length,output:path.join(out,filename),sha256:finalized.finalSha256,validation:'PASS'}));
