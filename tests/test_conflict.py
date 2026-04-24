import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory_backends import RedisMemory

print("Testing Redis conflict handling...")

mem = RedisMemory("test_conflict")

# Test mandatory rubric conflict
mem.save_profile_fact("allergy", "sua bo")
result = mem.save_profile_fact("allergy", "dau nhanh")

profile = mem.get_profile()
expected = "dau nhanh"
actual = profile["allergy"]
assert actual == expected, f"Expected {expected}, got {actual}"
print(f"[PASS] Conflict resolved: allergy = {actual}")

# Test profile history
history = mem.get_profile_history("allergy")
print(f"[PASS] Profile history has {len(history)} entries")
for h in history:
    print(f"  - key={h['key']}, value={h['value']}")

# Test delete
mem.save_profile_fact("name", "Minh")
mem.save_profile_fact("role", "developer")
profile = mem.get_profile()
assert "name" in profile and "role" in profile
mem.delete_profile_fact("name")
profile = mem.get_profile()
assert "name" not in profile, "delete failed"
print("[PASS] Profile deletion works")

print("\nAll conflict tests passed!")
