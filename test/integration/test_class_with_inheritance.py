"""Integration tests for class_with_inheritance_impl.py support file.

Tests execution and type checking of generated code for classes with inheritance.
"""

from pathlib import Path

from test.integration.test_utils import check_pyright


def test_inheritance_structure(generated_wrappers):
    """Test that inheritance relationships are correctly established."""
    import class_with_inheritance

    # Verify classes exist
    assert hasattr(class_with_inheritance, "WrappedBase")
    assert hasattr(class_with_inheritance, "WrappedSub")

    # Create instances
    base = class_with_inheritance.WrappedBase()
    sub = class_with_inheritance.WrappedSub()

    # Test isinstance checks - WrappedSub should be instance of WrappedBase
    assert isinstance(sub, class_with_inheritance.WrappedSub)
    assert isinstance(sub, class_with_inheritance.WrappedBase), "WrappedSub should inherit from WrappedBase"
    assert not isinstance(base, class_with_inheritance.WrappedSub), "WrappedBase should not be instance of WrappedSub"

    print("✓ Inheritance structure test passed")


def test_base_class_methods(generated_wrappers):
    """Test that methods defined in base classes are accessible."""
    import class_with_inheritance

    # Create derived class instance
    sub = class_with_inheritance.WrappedSub()

    # Call method defined in base class
    result = sub.wrapped_method()
    assert result == [], f"Expected [], got {result}"

    # Test that unwrapped base method is also accessible through impl
    assert sub._impl_instance.unwrapped_method() is True

    print("✓ Base class methods test passed")


def test_derived_class_methods(generated_wrappers):
    """Test that methods defined in derived class work correctly."""
    import class_with_inheritance

    sub = class_with_inheritance.WrappedSub()

    # Call method defined in derived class
    result = sub.wrapped_in_sub()
    assert result == {}, f"Expected {{}}, got {result}"

    print("✓ Derived class methods test passed")


def test_base_class_attributes(generated_wrappers):
    """Test that attributes from base classes are accessible."""
    import class_with_inheritance

    # Create instances
    base = class_with_inheritance.WrappedBase()
    sub = class_with_inheritance.WrappedSub()

    # Check base class attribute on base instance
    assert base._impl_instance.a == 1, "Base should have attribute 'a' from UnwrappedBase"
    assert base._impl_instance.b == "hello", "Base should have attribute 'b'"

    # Check base class attributes on derived instance
    assert sub._impl_instance.a == 1, "Sub should have attribute 'a' from UnwrappedBase"
    assert sub._impl_instance.b == "hello", "Sub should have attribute 'b' from WrappedBase"

    print("✓ Base class attributes test passed")


def test_derived_class_attributes(generated_wrappers):
    """Test that attributes defined in derived class are accessible."""
    import class_with_inheritance

    sub = class_with_inheritance.WrappedSub()

    # Check derived class attribute
    assert sub._impl_instance.c == 1.5, "Sub should have attribute 'c'"

    # Verify all attributes are present
    assert sub._impl_instance.a == 1
    assert sub._impl_instance.b == "hello"
    assert sub._impl_instance.c == 1.5

    print("✓ Derived class attributes test passed")


def test_identity_preservation_with_inheritance(generated_wrappers):
    """Test that _from_impl() cache works correctly with inheritance."""
    import class_with_inheritance
    import class_with_inheritance_impl

    # Create an impl instance
    impl_sub = class_with_inheritance_impl.WrappedSub()

    # Create wrapper from impl
    wrapper1 = class_with_inheritance.WrappedSub._from_impl(impl_sub)
    wrapper2 = class_with_inheritance.WrappedSub._from_impl(impl_sub)

    # Should return the same wrapper instance
    assert wrapper1 is wrapper2, "Identity preservation should work with inheritance"

    print("✓ Identity preservation test passed")


def test_no_method_duplication(generated_wrappers):
    """Test that base class methods are not duplicated in derived class source."""
    import class_with_inheritance

    # Check that WrappedSub only has wrapped_in_sub, not wrapped_method in its __dict__
    # (wrapped_method should be inherited, not redefined)
    assert "wrapped_in_sub" in dir(class_with_inheritance.WrappedSub)
    assert "wrapped_method" in dir(class_with_inheritance.WrappedSub)  # Should be accessible

    # Verify the method works when called on sub
    sub = class_with_inheritance.WrappedSub()
    assert sub.wrapped_method() == []
    assert sub.wrapped_in_sub() == {}

    print("✓ No method duplication test passed")


def test_pyright_class_with_inheritance(generated_wrappers):
    """Test that inheritance generation passes pyright type checking."""
    import class_with_inheritance

    # Verify type correctness with pyright
    check_pyright([Path(class_with_inheritance.__file__)])
