Fonts for PDF summaries in Indian languages
============================================

PDF files need a font that contains the letters of the language.

Windows: nothing to do. The app finds Nirmala.ttf in C:\Windows\Fonts.

Mac / Linux, or if you want the Noto look: download these free fonts (SIL Open Font
License) from https://fonts.google.com/noto and copy the .ttf files into THIS folder.
Use the exact file names below.

  Hindi, Marathi   NotoSansDevanagari-Regular.ttf   (and NotoSansDevanagari-Bold.ttf)
  Tamil            NotoSansTamil-Regular.ttf         (and NotoSansTamil-Bold.ttf)
  Telugu           NotoSansTelugu-Regular.ttf
  Kannada          NotoSansKannada-Regular.ttf
  Malayalam        NotoSansMalayalam-Regular.ttf
  Bengali          NotoSansBengali-Regular.ttf
  Gujarati         NotoSansGujarati-Regular.ttf

Static files are needed (not the variable "[wght]" versions). On the Google Fonts page,
choose "Download family" and look in the "static" folder.

Word (.docx) and Text (.txt) summaries do not need any font file.
You can also point PDF_FONT_DIR in .env at any folder that holds these files.
