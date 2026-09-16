import os
import shutil
import logging
from datetime import datetime
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from dotenv import load_dotenv

# LangChain & Embeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_groq import ChatGroq


load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

if not GROQ_API_KEY:
    raise ValueError("Missing Groq API Key.")


app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
UPLOAD_FOLDER = "./document_store"
CHROMA_DB_DIR = "./chroma_db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CHROMA_DB_DIR, exist_ok=True)

def clear_directory(directory: str):
    shutil.rmtree(directory, ignore_errors=True)
    os.makedirs(directory, exist_ok=True)


clear_directory(CHROMA_DB_DIR)
clear_directory(UPLOAD_FOLDER)

# Vector DB + LLM
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vector_db = Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=embeddings)
llm = ChatGroq(model_name="llama-3.1-8b-instant", groq_api_key=GROQ_API_KEY)

chat_history: List[dict] = []


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Routes
@app.get("/")
def root():
    return {"message": "Welcome to the chatbot backend!"}

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_location = os.path.join(UPLOAD_FOLDER, file.filename)
        with open(file_location, "wb") as f:
            f.write(await file.read())

        if file.filename.endswith(".pdf"):
            loader = PyPDFLoader(file_location)
        elif file.filename.endswith(".txt"):
            loader = TextLoader(file_location)
        else:
            return JSONResponse(
                content={"error": "Unsupported file format."},
                status_code=400
            )

        documents = loader.load()
        if not documents:
            raise HTTPException(status_code=400, detail="No text found in the document.")

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
        docs = text_splitter.split_documents(documents)

        
        for doc in docs:
            doc.metadata = {"source": file.filename}

        vector_db.add_documents(docs)

        return {"message": "File uploaded and indexed successfully.", "filename": file.filename}

    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files")
def list_uploaded_files():
    try:
        files = os.listdir(UPLOAD_FOLDER)
        return {"files": files}
    except Exception as e:
        return {"error": str(e)}

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(file_path, filename=filename)
@app.get("/search/")
async def search_query(query: str):
    try:
        
        greetings = {"hi", "hello", "hey", "yo", "howdy", "hola", "greetings"}
        if query.lower().strip() in greetings:
            answer = (
                "👋 Hello there! I'm here to help you understand your documents.\n\n"
                "📄 You can start by uploading a file on the Upload page.\n"
                "🔍 Then ask me any question about it right here!\n\n"
                "Need help getting started? Try asking:\n"
                "• *What is this document about?*\n"
                "• *Summarize the content.*\n"
                "• *What are the key points?*"
            )
            chat_history.append({
                "query": query,
                "answer": answer,
                "sources": [],
                "timestamp": datetime.utcnow().isoformat()
            })
            return {"query": query, "answer": answer, "sources": []}

        
        relevant_docs = vector_db.similarity_search(query)

        if not relevant_docs:
            return {"answer": "I couldn't find relevant information in the uploaded documents."}

        context = " ".join([doc.page_content for doc in relevant_docs])
        prompt = f"""
        You are a helpful AI assistant specialized in question answering using provided documents. 
        Use the context below to answer the user's question as accurately as possible. 
        If the answer is not present in the context, respond with:
        "I couldn't find relevant information in the uploaded documents."

        ---

        Context:
        {context}

        ---

        Question:
        {query}

        ---

        Answer:
        """

        ans = llm.invoke(prompt)

        chat_history.append({
            "query": query,
            "answer": ans.content,
            "sources": [doc.metadata.get("source", "Unknown") for doc in relevant_docs],
            "timestamp": datetime.utcnow().isoformat()
        })

        return {
            "query": query,
            "answer": ans.content,
            "sources": [doc.metadata.get("source", "Unknown") for doc in relevant_docs]
        }

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        return JSONResponse(content={"error": "Error processing query"}, status_code=500)


@app.get("/history/")
async def get_chat_history():
    return {"history": chat_history}

@app.get("/settings/models/")
def get_models():
    return {
        "models": [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
