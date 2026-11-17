type PublishedBook={
 id:string;title:string;author:string;category:string;genre:string;
 publisher:string;url:string;description:string;year?:number;series?:boolean;store?:boolean;
};
const series=(id:string,title:string,author:string,genre:string,url:string,description:string):PublishedBook=>({
 id,title,author,genre,url,description,category:'روايات مصرية',publisher:'روايات مصرية للجيب',series:true,
});
export const publishedBooks:PublishedBook[]=[
 series('paranormal','ما وراء الطبيعة','أحمد خالد توفيق','رعب','https://rewayatmasreya.com/collections/ma-waraa-al-tabia-ahmed-khaled-tawfik','حكايات رفعت إسماعيل مع الأساطير والظواهر الخارقة.'),
 series('impossible','رجل المستحيل','نبيل فاروق','مغامرة','https://rewayatmasreya.com/collections/ragol-al-mostaheel-nabil-farouk','أدهم صبري في مهمات المخابرات والمطاردات.'),
 series('future','ملف المستقبل','نبيل فاروق','خيال علمي','https://rewayatmasreya.com/collections/malaf-al-mostaqbal','نور الدين وفريقه في مغامرات علمية وألغاز مستقبلية.'),
 series('fantasia','فانتازيا','أحمد خالد توفيق','فانتازيا','https://rewayatmasreya.com/collections/فانتازيا','عبير تستكشف عوالم الأدب والتاريخ والخيال.'),
 series('safari','سافاري','أحمد خالد توفيق','مغامرة','https://rewayatmasreya.net/series/سافاري/','طبيب مصري يواجه أمراضًا وألغازًا في مغامراته بأفريقيا.'),
 series('flash','فلاش','خالد الصفتي','كوميكس','https://rewayatmasreya.com/collections/flash-khaled-el-safty','قصص مصوّرة ومواقف ساخرة وألغاز.'),
 {id:'egy-blue',title:'الفيل الأزرق',author:'أحمد مراد',category:'روايات مصرية',genre:'رعب',url:'https://www.jarir.com/arabic-books-jbb1650na003.html',publisher:'دار الشروق · قارئ جرير',description:'طبيب نفسي يعود إلى مستشفى العباسية ويواجه صديقًا قديمًا وقضية غامضة.',store:true},
 {id:'egy-mice',title:'في ممر الفئران',author:'أحمد خالد توفيق',category:'روايات مصرية',genre:'خيال علمي',url:'https://www.jarir.com/arabic-books-jbb6990na016.html',publisher:'الكرمة · قارئ جرير',description:'خيال ديستوبي عن عالم يسيطر عليه الظلام.',store:true},
 {id:'egy-awda',title:'عودة الروح',author:'توفيق الحكيم',category:'روايات مصرية',genre:'أدب كلاسيكي',year:1933,url:'https://downloads.hindawi.org/books/31425393.pdf',publisher:'مؤسسة هنداوي',description:'حياة أسرة مصرية في القاهرة في السنوات التي سبقت ثورة 1919.'},
 {id:'egy-palace',title:'القصر المسحور',author:'توفيق الحكيم وطه حسين',category:'روايات مصرية',genre:'فانتازيا',year:1936,url:'https://downloads.hindawi.org/books/84275792.pdf',publisher:'مؤسسة هنداوي',description:'عمل مشترك يستعيد عالم شهرزاد وشهريار بعد الليلة الألف.'},
 {id:'world-dracula',title:'دراكولا / Dracula',author:'Bram Stoker',category:'روايات عالمية',genre:'رعب',year:1897,url:'https://www.gutenberg.org/ebooks/345',publisher:'Project Gutenberg',description:'رواية رعب قوطية تُروى عبر رسائل ويوميات.'},
 {id:'world-frankenstein',title:'فرانكنشتاين / Frankenstein',author:'Mary Shelley',category:'روايات عالمية',genre:'رعب',year:1818,url:'https://www.gutenberg.org/ebooks/84',publisher:'Project Gutenberg',description:'عالِم يخلق كائنًا حيًا ويواجه تبعات تجربته.'},
 {id:'world-jekyll',title:'الدكتور جيكل والسيد هايد',author:'Robert Louis Stevenson',category:'روايات عالمية',genre:'رعب',year:1886,url:'https://www.gutenberg.org/ebooks/43',publisher:'Project Gutenberg',description:'تجربة تكشف الجانب الخفي من شخصية طبيب في لندن.'},
 {id:'world-alice',title:'أليس في بلاد العجائب',author:'Lewis Carroll',category:'روايات عالمية',genre:'فانتازيا',year:1865,url:'https://www.gutenberg.org/ebooks/11',publisher:'Project Gutenberg',description:'مغامرة في عالم خيالي تبدأ بمطاردة أرنب أبيض.'},
 {id:'world-monte-cristo',title:'كونت مونت كريستو',author:'Alexandre Dumas',category:'روايات عالمية',genre:'مغامرة',year:1844,url:'https://www.gutenberg.org/ebooks/1184',publisher:'Project Gutenberg',description:'حكاية سجين يهرب ويعود بهوية جديدة.'},
 {id:'egy-zenab',title:'زينب',author:'محمد حسين هيكل',category:'روايات مصرية',genre:'أدب كلاسيكي',year:1914,url:'https://downloads.hindawi.org/books/28493759.pdf',publisher:'مؤسسة هنداوي',description:'من الروايات المبكرة في الأدب المصري الحديث، عن الريف والحب والتقاليد.'},
 {id:'egy-east',title:'عصفور من الشرق',author:'توفيق الحكيم',category:'روايات مصرية',genre:'أدب كلاسيكي',year:1938,url:'https://downloads.hindawi.org/books/74917046.pdf',publisher:'مؤسسة هنداوي',description:'رواية مصرية عن التقاء الشرق والغرب وتجربة الشاب محسن في باريس.'},
 {id:'world-pride',title:'كبرياء وتحامل / Pride and Prejudice',author:'Jane Austen',category:'روايات عالمية',genre:'أدب كلاسيكي',year:1813,url:'https://www.gutenberg.org/ebooks/1342',publisher:'Project Gutenberg',description:'رواية كلاسيكية إنجليزية عن العائلة والمكانة الاجتماعية والحب.'},
 {id:'world-time',title:'آلة الزمن / The Time Machine',author:'H. G. Wells',category:'روايات عالمية',genre:'خيال علمي',year:1895,url:'https://www.gutenberg.org/ebooks/35',publisher:'Project Gutenberg',description:'من كلاسيكيات الخيال العلمي والرحلة إلى مستقبل بعيد.'},
 {id:'world-sherlock',title:'مغامرات شيرلوك هولمز',author:'Arthur Conan Doyle',category:'روايات عالمية',genre:'غموض',year:1892,url:'https://www.gutenberg.org/ebooks/1661',publisher:'Project Gutenberg',description:'مجموعة قصص بوليسية عالمية لشيرلوك هولمز.'},
];
