import os
from datetime import datetime
from PyPDF2 import PdfReader
from docx import Document

def extract_text_from_txt(file_path: str) -> str:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read().strip()
    except Exception as e:
        return f"读取TXT失败: {str(e)}"

def extract_text_from_pdf(file_path: str) -> str:
    try:
        with open(file_path, 'rb') as f:
            reader = PdfReader(f)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text.strip()
    except Exception as e:
        return f"读取PDF失败: {str(e)}"

def extract_text_from_docx(file_path: str) -> str:
    try:
        doc = Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"读取Word失败: {str(e)}"

def extract_text_from_file(file_path: str) -> str:
    filename = file_path.lower()
    
    if filename.endswith('.txt'):
        return extract_text_from_txt(file_path)
    elif filename.endswith('.pdf'):
        return extract_text_from_pdf(file_path)
    elif filename.endswith('.docx'):
        return extract_text_from_docx(file_path)
    else:
        return f"不支持的文件格式"

def parse_documents_in_folder(folder_path: str) -> list:
    result = []
    supported_extensions = ('.txt', '.pdf', '.docx')
    
    if not os.path.isdir(folder_path):
        return [{"error": f"路径不是有效的文件夹: {folder_path}"}]
    
    for root, _, files in os.walk(folder_path):
        for filename in files:
            if filename.lower().endswith(supported_extensions):
                file_path = os.path.join(root, filename)
                
                try:
                    file_stat = os.stat(file_path)
                    modify_time = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    
                    content = extract_text_from_file(file_path)
                    
                    result.append({
                        "filename": filename,
                        "file_path": file_path,
                        "content": content,
                        "modify_time": modify_time
                    })
                except Exception as e:
                    result.append({
                        "filename": filename,
                        "file_path": file_path,
                        "content": f"处理文件时发生错误: {str(e)}",
                        "modify_time": "未知"
                    })
    
    return result

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 2:
        print("用法: python document_parser.py <文件夹路径>")
        sys.exit(1)
    
    folder_path = sys.argv[1]
    documents = parse_documents_in_folder(folder_path)
    
    print(f"共找到 {len(documents)} 个文档:")
    for doc in documents:
        print(f"\n文件名: {doc['filename']}")
        print(f"路径: {doc['file_path']}")
        print(f"修改时间: {doc['modify_time']}")
        print(f"内容预览: {doc['content'][:200]}...")