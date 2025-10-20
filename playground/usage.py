from my_library import Bar, accepts_bar

b = Bar("hello")
b2 = accepts_bar(b)
assert b2._impl_instance is b._impl_instance
assert b2 is b

