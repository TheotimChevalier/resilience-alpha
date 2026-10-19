# Fichier : rag/assistant.py
import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

DOC_PATH = os.path.join(os.path.dirname(__file__), "procedure_crise.md")
LLM_MODEL = "llama3.2"
EMBED_MODEL = "nomic-embed-text"

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def main():
    print("[*] Chargement de la documentation opérationnelle...")
    loader = TextLoader(DOC_PATH, encoding="utf-8")
    docs = loader.load()

    text_splitter = CharacterTextSplitter(chunk_size=300, chunk_overlap=50)
    splits = text_splitter.split_documents(docs)

    print(f"[*] Indexation vectorielle avec le modèle {EMBED_MODEL}...")
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)
    vectorstore = Chroma.from_documents(documents=splits, embedding=embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 2})

    print(f"[*] Initialisation du LLM {LLM_MODEL}...")
    llm = OllamaLLM(model=LLM_MODEL, temperature=0.1)

    template = """Tu es l'assistant IA opérationnel de PROJECT RESILIENCE-ALPHA.
Réponds aux questions de l'opérateur en utilisant UNIQUEMENT le contexte technique fourni ci-dessous.
Reste concis, précis et factuel.

Contexte technique :
{context}

Question de l'opérateur :
{question}"""

    prompt = ChatPromptTemplate.from_template(template)

    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    print("\n[+] Assistant RAG opérationnel. Posez votre question (ou tapez 'exit') :\n")

    while True:
        query = input("Opérateur > ")
        if query.strip().lower() in ["exit", "quit"]:
            break
        if not query.strip():
            continue

        response = rag_chain.invoke(query)
        print(f"\nAssistant IA > {response}\n")

if __name__ == "__main__":
    main()