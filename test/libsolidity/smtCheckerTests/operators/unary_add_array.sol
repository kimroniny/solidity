pragma experimental SMTChecker;

contract C
{
	uint[] array;
	function f(uint x) public {
		array[x] = 2;
		uint a = ++array[x];
		assert(array[x] == 3);
		assert(a == 3);
		uint b = array[x]++;
		assert(array[x] == 4);
		// Should fail.
		assert(b < 3);
	}
}
// ----
// Warning 6328: (240-253): CHC: Assertion violation happens here.\nCounterexample:\narray = []\nx = 0\n\n\nTransaction trace:\nconstructor()\nState: array = []\nf(0)
