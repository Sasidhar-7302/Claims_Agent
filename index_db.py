from app.vector_store import get_vector_store
import sys

def main():
    print("Initializing vector store...")
    store = get_vector_store()
    
    print("Indexing policies...")
    count = store.index_policies(force_reindex=True)
    
    print(f"Successfully indexed {count} policy chunks.")
    
    # Test query
    print("Running test query...")
    results = store.query("warranty coverage for water damage")
    for res in results:
        print(f"Match ({res['distance']:.4f}): {res['content'][:50]}...")

if __name__ == "__main__":
    main()
